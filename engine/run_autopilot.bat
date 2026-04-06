@echo off
REM DeepCast AI Autopilot — Windowsタスクスケジューラ用バッチファイル
REM
REM タスクスケジューラ登録コマンド（管理者PowerShellで実行）:
REM   schtasks /create /tn "DeepCast_Autopilot" /tr "G:\マイドライブ\株式会社　礼\運用中\8_ディープキャスト\engine\run_autopilot.bat" /sc daily /st 08:00 /ri 1440 /f
REM
REM 2日に1回にする場合:
REM   schtasks /create /tn "DeepCast_Autopilot" /tr "G:\マイドライブ\株式会社　礼\運用中\8_ディープキャスト\engine\run_autopilot.bat" /sc daily /mo 2 /st 08:00 /f

cd /d "G:\マイドライブ\株式会社　礼\運用中\8_ディープキャスト\engine"

REM Python仮想環境があれば有効化（なければスキップ）
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM 統合Autopilot実行（日本語1エピソード）
python "%~dp0..\scripts\autopilot.py" --count 1

REM ログ出力
echo [%date% %time%] Autopilot completed >> autopilot_history.log
