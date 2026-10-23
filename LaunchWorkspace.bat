@echo off

:: Dynamically locate the latest Claude installation folder
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-AppxPackage *Claude* | Select-Object -Last 1).InstallLocation"`) do set "CLAUDE_DIR=%%I"

:: Claude Instance (frag)
start "" "%CLAUDE_DIR%\app\Claude.exe" --user-data-dir="%USERPROFILE%\.claude-instance-frag"

:: Claude Instance (made)
start "" "%CLAUDE_DIR%\app\Claude.exe" --user-data-dir="%USERPROFILE%\.claude-instance-made"

:: MCP Server (primary)
start "" /B "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -WindowStyle Hidden -Command "Set-Location 'C:\Users\Olabode Nathaniel\Code\obsidian-mcp'; & '.venv\Scripts\obsidian-mcp.exe'"

:: MCP Server (web/logs)
start "" /B "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -WindowStyle Hidden -Command "Set-Location 'C:\Users\Olabode Nathaniel\Code\obsidian-mcp'; & '.venv\Scripts\obsidian-mcp-web.exe'"

:: Obsidian
start "" "C:\Users\Olabode Nathaniel\Downloads\ObsidianPortable\App\Obsidian\Obsidian.exe"