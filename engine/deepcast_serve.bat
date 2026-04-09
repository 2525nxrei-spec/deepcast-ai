@echo off
REM ============================================================
REM DeepCast Engine — 自律スケジューラ起動バッチ
REM Windowsタスクスケジューラから毎日実行される
REM ============================================================

cd /d "D:\株式会社　礼\運用中\8_ディープキャスト\engine"

REM ログファイルに日時を記録
echo [%date% %time%] DeepCast Engine starting... >> deepcast_serve.log

REM main.py serve でスケジューラ+APIサーバーを起動
REM pythonw で起動するとウィンドウなしで動作する
"C:\Users\0808r\AppData\Local\Programs\Python\Python312\python.exe" main.py serve >> deepcast_serve.log 2>&1
