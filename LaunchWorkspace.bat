@echo off

:: Dynamically locate the latest Claude installation folder
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-AppxPackage *Claude* | Select-Object -Last 1).InstallLocation"`) do set "CLAUDE_DIR=%%I"

:: Claude Instance (frag)
start "" "%CLAUDE_DIR%\app\Claude.exe" --user-data-dir="%USERPROFILE%\.claude-instance-tinu"

:: Claude Instance (made)
start "" "%CLAUDE_DIR%\app\Claude.exe" --user-data-dir="%USERPROFILE%\.claude-instance-mom"

:: MCP Server (primary)
start "" /B "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -WindowStyle Hidden -Command "Set-Location 'C:\Users\Olabode Nathaniel\Code\obsidian-mcp-idea-vault'; & '.venv\Scripts\obsidian-mcp.exe'"

:: MCP Server (web/logs)
start "" /B "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -WindowStyle Hidden -Command "Set-Location 'C:\Users\Olabode Nathaniel\Code\obsidian-mcp-idea-vault'; & '.venv\Scripts\obsidian-mcp-web.exe'"

:: Obsidian
start "" "obsidian://open?path=C%%3A%%5CUsers%%5COlabode%%20Nathaniel%%5COneDrive%%5CApps%%5Cremotely-save%%5CIdeas%%5CAcoustic%%20Emotion%%20Recognition"