$logDir = "D:\Coding\dao_vang\scripts\logs"
Start-Transcript -Path "$logDir\check_tasks.log" -Force
Get-ScheduledTask | Where-Object { $_.TaskName -like "DaoVang*" } | Select-Object TaskName, State, TaskPath
Write-Host "--- info ---"
Get-ScheduledTaskInfo -TaskName "DaoVangScanner" -ErrorAction SilentlyContinue
Get-ScheduledTaskInfo -TaskName "DaoVangWebUI" -ErrorAction SilentlyContinue
Stop-Transcript
