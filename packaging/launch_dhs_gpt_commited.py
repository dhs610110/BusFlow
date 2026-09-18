"""Desktop wrapper for the pinned upstream application. No API calls at startup tests."""
import os, sys, threading, traceback, webbrowser
from pathlib import Path
from datetime import datetime
BASE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def load_key():
    p=BASE/'.env'
    if p.exists():
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip()=='DATA_API_KEY' and value.strip():os.environ.setdefault('DATA_API_KEY',value.strip().strip('\"').strip("'"))

def main():
    load_key()
    from app_integrated_dhs_gpt_commited import app,Server,QuietHandler
    from wsgiref.simple_server import make_server
    # Request any free local port; do not kill or reuse unrelated servers.
    server=make_server('127.0.0.1',0,app,server_class=Server,handler_class=QuietHandler)
    address=f'http://127.0.0.1:{server.server_port}'
    if '--headless' in sys.argv:
        path=BASE/'ready.txt';path.write_text(address,encoding='utf-8')
        try:server.serve_forever()
        finally:path.unlink(missing_ok=True);server.server_close()
        return
    import tkinter as tk
    from tkinter import simpledialog,messagebox
    window=tk.Tk();window.title('GTA 실행 중');window.geometry('440x250');window.resizable(False,False)
    window.configure(bg='#111827')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    tk.Label(window,text='GTA',font=('Arial',28,'bold'),fg='#ff6262',bg='#111827').pack(pady=(15,4))
    tk.Label(window,text='브라우저에서 이용하세요. 이 창을 닫으면 종료됩니다.',fg='white',bg='#111827').pack(pady=5)
    state=tk.StringVar()
    def refresh():state.set('버스 API 키 설정됨 · 실제 응답은 조회 시 확인' if os.getenv('DATA_API_KEY') else '실시간 버스 조회는 API 키 설정이 필요합니다.')
    refresh();tk.Label(window,textvariable=state,fg='#d3dce9',bg='#111827').pack(pady=5)
    def key_settings():
        key=simpledialog.askstring('API 키 설정','승인받은 DATA_API_KEY를 붙여넣으세요.\n이 PC에 저장되며 다른 곳으로 전송하지 않습니다.\n버스 조회 시 해당 API 제공기관에 사용됩니다.',show='*',parent=window)
        if key is None:return
        key=key.strip()
        if not key or '\n' in key or '\r' in key:
            messagebox.showerror('입력 확인','API 키를 한 줄로 입력해주세요.',parent=window);return
        try:
            p=BASE/'.env';lines=p.read_text(encoding='utf-8-sig').splitlines() if p.exists() else []
            lines=[l for l in lines if l.partition('=')[0].strip()!='DATA_API_KEY']
            p.write_text('\n'.join(lines+['DATA_API_KEY='+key])+'\n',encoding='utf-8')
            os.environ['DATA_API_KEY']=key;app.external.cache.clear();refresh()
        except OSError:messagebox.showerror('저장 실패','쓰기 가능한 폴더에 압축을 풀었는지 확인해주세요.',parent=window)
    frame=tk.Frame(window,bg='#111827');frame.pack(pady=12)
    tk.Button(frame,text='웹 화면 열기',command=lambda:webbrowser.open(address),width=15).pack(side='left',padx=6)
    tk.Button(frame,text='API 키 설정',command=key_settings,width=15).pack(side='left',padx=6)
    tk.Label(window,text='처음 설정한 키는 다음 실행에도 유지됩니다.',fg='#aab7ca',bg='#111827').pack()
    def close():
        server.shutdown();server.server_close();window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    window.after(400,lambda:webbrowser.open(address));window.mainloop()

if __name__=='__main__':
    try:main()
    except Exception:
        (BASE/'GTA_error.log').write_text(traceback.format_exc(),encoding='utf-8')
        if '--headless' in sys.argv:raise
        try:
            import tkinter as tk
            from tkinter import messagebox
            w=tk.Tk();w.withdraw();messagebox.showerror('GTA 실행 오류','GTA_error.log에 오류 내용을 저장했습니다. 실행 파일과 _internal 폴더가 함께 있는지 확인해주세요.');w.destroy()
        except Exception:pass
