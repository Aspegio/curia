// Static assets answer a Range request with the whole file, and Safari will
// not play a video it cannot fetch in parts, so /media/* comes through here
// (run_worker_first in deploy.sh) to be answered 206. Everything else,
// /github's redirects included, is served by the assets alone. The assets
// response carries no length, so deploy.sh passes each file's size in SIZES.
export default {
  async fetch(request, env) {
    const res = await env.ASSETS.fetch(request);
    const size = Number(res.headers.get("Content-Length")) || (env.SIZES || {})[new URL(request.url).pathname];
    const m = /^bytes=(\d*)-(\d*)$/.exec((request.headers.get("Range") || "").trim());
    if (!m || (m[1] === "" && m[2] === "") || res.status !== 200 || !res.body || !(size > 0)) {
      const headers = new Headers(res.headers);
      headers.set("Accept-Ranges", "bytes");
      return new Response(res.body, { status: res.status, headers });
    }

    let start, end;
    if (m[1] === "") { start = Math.max(0, size - Number(m[2])); end = size - 1; }
    else { start = Number(m[1]); end = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1); }
    if (start > end || start >= size) {
      await res.body.cancel();
      return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    }

    const length = end - start + 1;
    const { readable, writable } = new FixedLengthStream(length);
    res.body.pipeThrough(slice(start, end + 1)).pipeTo(writable);
    const headers = new Headers(res.headers);
    headers.set("Accept-Ranges", "bytes");
    headers.set("Content-Range", `bytes ${start}-${end}/${size}`);
    return new Response(readable, { status: 206, headers });
  },
};

// Pass through only bytes [from, to) of the stream, then stop reading it.
function slice(from, to) {
  let pos = 0;
  return new TransformStream({
    transform(chunk, controller) {
      const a = Math.max(from - pos, 0), b = Math.min(to - pos, chunk.byteLength);
      if (a < b) controller.enqueue(chunk.subarray(a, b));
      pos += chunk.byteLength;
      if (pos >= to) controller.terminate();
    },
  });
}
