# -*- coding: utf-8 -*-
"""
天天采配清单-PDF转Excel —— 网页版（单端口 HTTP 服务）

· 转换核心：converter_core.py（与 exe 版完全相同，未改动）
· 前端：static/index.html
· 上传的 PDF 转换完立即删除，结果文件保留 30 分钟后清理
· 可选访问口令：环境变量 ACCESS_CODE
· 监听 PORT（默认 8000），绑定 0.0.0.0
"""

import os
import re
import time
import uuid
import shutil
import zipfile
import tempfile
import threading
import traceback

from flask import Flask, request, jsonify, send_file

import converter_core as cc

BASE = os.path.dirname(os.path.abspath(__file__))
TMP_ROOT = os.path.join(tempfile.gettempdir(), "pdf2xlsx_web")
ACCESS_CODE = os.environ.get("ACCESS_CODE", "").strip()
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
RESULT_TTL = int(os.environ.get("RESULT_TTL", "1800"))

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

_jobs = {}
_lock = threading.Lock()


def _safe_name(s):
    s = re.sub(r'[\\/:*?"<>|\r\n\t\x00-\x1f]', "_", s or "").strip(" .")
    return s[:80]


def _emit(job, ev):
    with _lock:
        job["seq"] += 1
        ev = dict(ev)
        ev["seq"] = job["seq"]
        job["events"].append(ev)


def _unique_path(folder, name, used):
    root, ext = os.path.splitext(name)
    path, k = os.path.join(folder, name), 1
    while os.path.exists(path) or os.path.normcase(path) in used:
        path = os.path.join(folder, "%s(%d)%s" % (root, k, ext))
        k += 1
    used.add(os.path.normcase(path))
    return path


def _worker(jid, pdfs, layout, custom):
    job = _jobs.get(jid)
    if not job:
        return
    jobdir = job["dir"]
    outdir = os.path.join(jobdir, "_result")
    os.makedirs(outdir, exist_ok=True)

    n = len(pdfs)
    multi = n > 1
    used, final_files = set(), []
    ok, fail, errs = 0, 0, []

    _emit(job, {"type": "log", "level": "dim",
                "text": "本次转换 %d 个文件 · %s" %
                        (n, "单工作表" if layout == "single" else "多工作表")})

    for i, (orig, path) in enumerate(pdfs, 1):
        _emit(job, {"type": "file_state", "index": i - 1, "state": "run"})
        _emit(job, {"type": "log", "level": "info", "text": "[%d/%d] %s" % (i, n, orig)})

        def prog(cur, total, txt, _i=i, _name=orig):
            frac = (_i - 1 + cur / float(max(total, 1))) / n
            _emit(job, {"type": "progress", "value": round(frac * 100, 1),
                        "text": "%s：%s" % (_name, txt)})

        try:
            r = cc.convert(
                path, jobdir, progress=prog,
                log=lambda t: _emit(job, {"type": "log", "level": "dim", "text": "    " + t}),
                layout_mode=layout)

            stem = os.path.splitext(orig)[0]
            if custom:
                stem = custom + "_" + stem if multi else custom
            target = _unique_path(outdir, _safe_name(stem or "商品清单") + ".xlsx", used)
            shutil.move(r["output"], target)
            final_files.append(target)

            for w in r["warnings"]:
                _emit(job, {"type": "log", "level": "warn", "text": "    ⚠ " + w})
            _emit(job, {"type": "log", "level": "ok",
                        "text": "    ✓ %s（%d 行）" % (os.path.basename(target), r["rows"])})
            _emit(job, {"type": "file_state", "index": i - 1, "state": "done"})
            ok += 1
        except Exception as e:
            fail += 1
            errs.append("%s：%s" % (orig, e))
            _emit(job, {"type": "file_state", "index": i - 1, "state": "fail"})
            _emit(job, {"type": "log", "level": "err", "text": "    ✗ 失败：%s" % e})
            if not isinstance(e, cc.ConvertError):
                _emit(job, {"type": "log", "level": "dim",
                            "text": "    " + traceback.format_exc().replace("\n", "\n    ")})
        finally:
            try:
                os.remove(path)          # 上传的 PDF 用完即删
            except OSError:
                pass

    result, filename = None, None
    if final_files:
        if len(final_files) == 1:
            result, filename = final_files[0], os.path.basename(final_files[0])
        else:
            zp = _unique_path(jobdir, (_safe_name(custom) or "转换结果") + ".zip", set())
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                for p in final_files:
                    z.write(p, arcname=os.path.basename(p))
            result, filename = zp, os.path.basename(zp)
        with _lock:
            job["result"], job["filename"] = result, filename

    if ok and fail == 0:
        _emit(job, {"type": "progress", "value": 100, "text": "转换完成：成功 %d 个" % ok})
    _emit(job, {"type": "done", "ok": ok, "fail": fail, "errs": errs,
                "download": ("/api/download/" + jid) if result else None,
                "filename": filename})
    with _lock:
        job["busy"] = False
        job["finished"] = time.time()


def _gc():
    while True:
        time.sleep(60)
        with _lock:
            dead = [k for k, j in _jobs.items()
                    if not j["busy"]
                    and time.time() - (j.get("finished") or j["created"]) > RESULT_TTL]
            for k in dead:
                shutil.rmtree(_jobs[k]["dir"], ignore_errors=True)
                del _jobs[k]


@app.get("/")
def index():
    return send_file(os.path.join(BASE, "static", "index.html"))


@app.get("/api/config")
def config():
    # codeOk 只回布尔值，不回口令本身；前端用它判断链接里的口令是否有效
    supplied = request.headers.get("X-Access-Code", "")
    return jsonify(needCode=bool(ACCESS_CODE),
                   codeOk=(not ACCESS_CODE or supplied == ACCESS_CODE),
                   maxUploadMB=MAX_UPLOAD_MB,
                   version="v1.5-web")


@app.post("/api/jobs")
def create_job():
    if ACCESS_CODE and request.headers.get("X-Access-Code", "") != ACCESS_CODE:
        return jsonify(ok=False, msg="访问口令错误"), 403

    uploads = [f for f in request.files.getlist("files") if f and f.filename]
    if not uploads:
        return jsonify(ok=False, msg="没有收到文件"), 400
    if len(uploads) > 30:
        return jsonify(ok=False, msg="一次最多处理 30 个文件"), 400

    layout = request.form.get("layout", "single")
    if layout not in ("single", "separate"):
        layout = "single"
    custom = _safe_name(request.form.get("name", ""))

    jid = uuid.uuid4().hex[:12]
    jobdir = os.path.join(TMP_ROOT, jid)
    os.makedirs(jobdir, exist_ok=True)

    pdfs = []
    for i, f in enumerate(uploads, 1):
        orig = _safe_name(os.path.basename(f.filename))
        if not orig.lower().endswith(".pdf"):
            shutil.rmtree(jobdir, ignore_errors=True)
            return jsonify(ok=False, msg="仅支持 PDF 文件：%s" % orig), 400
        # 每个文件放独立子目录，保留原始文件名，转换日志里不会出现内部编号
        inbox = os.path.join(jobdir, "in", "%03d" % i)
        os.makedirs(inbox, exist_ok=True)
        stored = os.path.join(inbox, orig)
        f.save(stored)
        pdfs.append((orig, stored))

    job = {"events": [], "seq": 0, "busy": True, "dir": jobdir,
           "created": time.time(), "finished": None,
           "result": None, "filename": None, "custom": custom}
    with _lock:
        _jobs[jid] = job
    threading.Thread(target=_worker, args=(jid, pdfs, layout, custom), daemon=True).start()
    return jsonify(ok=True, id=jid)


@app.get("/api/jobs/<jid>/events")
def events(jid):
    if ACCESS_CODE and request.headers.get("X-Access-Code", "") != ACCESS_CODE:
        return jsonify(ok=False, msg="访问口令错误"), 403
    try:
        after = int(request.args.get("after", "0"))
    except ValueError:
        after = 0
    with _lock:
        job = _jobs.get(jid)
        if not job:
            return jsonify(ok=False, msg="任务不存在或已过期"), 404
        evs = [e for e in job["events"] if e["seq"] > after]
        busy = job["busy"]
    return jsonify(ok=True, events=evs, busy=busy)


@app.get("/api/download/<jid>")
def download(jid):
    if ACCESS_CODE:
        supplied = request.headers.get("X-Access-Code") or request.args.get("code", "")
        if supplied != ACCESS_CODE:
            return jsonify(ok=False, msg="访问口令错误"), 403
    with _lock:
        job = _jobs.get(jid)
        result = job["result"] if job else None
        filename = job["filename"] if job else None
    if not result or not os.path.isfile(result):
        return jsonify(ok=False, msg="结果文件不存在或已过期"), 404
    return send_file(result, as_attachment=True, download_name=filename)


@app.errorhandler(413)
def too_large(_e):
    return jsonify(ok=False, msg="上传文件超过 %d MB 限制" % MAX_UPLOAD_MB), 413


@app.errorhandler(404)
def not_found(_e):
    return jsonify(ok=False, msg="接口不存在"), 404


if __name__ == "__main__":
    os.makedirs(TMP_ROOT, exist_ok=True)
    threading.Thread(target=_gc, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    threads = int(os.environ.get("THREADS", "4"))
    if not ACCESS_CODE:
        print("!!! 警告：ACCESS_CODE 未设置，服务无口令对外开放 !!!", flush=True)
    print("天天采配清单-PDF转Excel 网页版 http://%s:%d" % (host, port), flush=True)

    if os.environ.get("DEV_SERVER") == "1":
        # 本地调试才用 Flask 自带服务器
        app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
    else:
        from waitress import serve
        serve(app, host=host, port=port, threads=threads,
              channel_timeout=int(os.environ.get("CHANNEL_TIMEOUT", "300")),
              max_request_body_size=(MAX_UPLOAD_MB + 2) * 1024 * 1024)
