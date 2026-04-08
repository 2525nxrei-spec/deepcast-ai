# ============================================================
# DeepCast Engine — タスクスケジューラ登録スクリプト
# 管理者権限で実行すること（右クリック→管理者として実行）
# ============================================================

$taskName = "DeepCast_Engine"
$batPath = "G:\マイドライブ\株式会社　礼\運用中\8_ディープキャスト\engine\deepcast_serve.bat"
$workDir = "G:\マイドライブ\株式会社　礼\運用中\8_ディープキャスト\engine"

# 既存タスクがあれば削除
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "既存タスク '$taskName' を削除しました。"
}

# アクション: バッチファイルを実行
$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $workDir

# トリガー: 毎日6:00に起動
$trigger = New-ScheduledTaskTrigger -Daily -At "06:00"

# 設定: PCスリープから復帰して実行、電源接続時のみ等
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 23)

# タスク登録
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "DeepCast AI 自律コンテンツ生成エンジン（毎日6:00起動）" `
    -RunLevel Highest

Write-Host ""
Write-Host "=== タスクスケジューラ登録完了 ==="
Write-Host "タスク名: $taskName"
Write-Host "実行時刻: 毎日 06:00"
Write-Host "バッチ: $batPath"
Write-Host ""
Write-Host "確認: タスクスケジューラを開いて '$taskName' が登録されていることを確認してください。"
Write-Host "手動テスト: schtasks /run /tn '$taskName'"
