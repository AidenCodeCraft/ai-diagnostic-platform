# Docker 镜像加速器配置脚本
# 运行方式：以管理员身份打开 PowerShell，执行：
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# .\setup-mirror.ps1

$daemonConfigPath = "$env:USERPROFILE\.docker\daemon.json"

$config = @{
    "registry-mirrors" = @(
        "https://docker.1ms.run",
        "https://docker.xuanyuan.me"
    )
}

# 创建目录（如果不存在）
$dir = Split-Path $daemonConfigPath -Parent
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# 写入配置
$config | ConvertTo-Json -Depth 3 | Set-Content -Path $daemonConfigPath -Encoding UTF8

Write-Host "✅ Docker 镜像加速器已配置" -ForegroundColor Green
Write-Host ""
Write-Host "下一步："
Write-Host "1. 打开 Docker Desktop"
Write-Host "2. 点击右上角齿轮 ⚙ → Docker Engine"
Write-Host "3. 确认 registry-mirrors 已出现"
Write-Host "4. 点击 'Apply & Restart'"
Write-Host "5. 重启后执行：docker compose up -d --build"
Write-Host ""
Write-Host "当前配置内容："
Get-Content $daemonConfigPath
