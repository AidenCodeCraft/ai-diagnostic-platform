# ============================================================================
# AI Diagnostic Platform — 本地 K8s 一键部署脚本 (Windows PowerShell)
# ============================================================================
# 适用：Docker Desktop K8s / minikube / kind
# 流程：docker build → kubectl apply → 等待就绪 → port-forward
# ============================================================================

param(
    [switch]$SkipBuild,       # 跳过 Docker 构建
    [switch]$Clean,           # 先删除旧部署再重新创建
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 8080
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Location).Path
$namespace = "ai-diagnostic"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AI Diagnostic Platform — 本地 K8s 部署" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── 前置检查 ────────────────────────────────────────────

Write-Host ">>> 1. 检查环境" -ForegroundColor White

# Docker
try {
    docker info 2>&1 | Out-Null
    Write-Host "  [OK] Docker 可用" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Docker 未运行，请先启动 Docker Desktop" -ForegroundColor Red
    exit 1
}

# kubectl
try {
    $cluster = kubectl cluster-info 2>&1 | Select-String "is running at"
    if ($cluster) {
        Write-Host "  [OK] kubectl 已连接集群" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] kubectl 无法连接集群" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  [FAIL] kubectl 未安装或无法连接" -ForegroundColor Red
    exit 1
}

# ── 清理旧部署 ──────────────────────────────────────────

if ($Clean) {
    Write-Host ""
    Write-Host ">>> 清理旧部署" -ForegroundColor Yellow
    kubectl delete namespace $namespace --ignore-not-found 2>&1 | Out-Null
    Start-Sleep -Seconds 3
}

# ── 构建镜像 ────────────────────────────────────────────

if (-not $SkipBuild) {
    Write-Host ""
    Write-Host ">>> 2. 构建 Docker 镜像" -ForegroundColor White

    # 后端镜像
    Write-Host "  构建 ai-diagnostic-backend:local ..." -ForegroundColor Gray
    docker build -t ai-diagnostic-backend:local -f backend/Dockerfile . 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] 后端镜像构建失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] 后端镜像构建成功" -ForegroundColor Green

    # 前端镜像
    Write-Host "  构建 ai-diagnostic-frontend:local ..." -ForegroundColor Gray
    docker build -t ai-diagnostic-frontend:local -f apps/web/Dockerfile apps/web/ 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] 前端镜像构建失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] 前端镜像构建成功" -ForegroundColor Green
}

# ── 部署到 K8s ──────────────────────────────────────────

Write-Host ""
Write-Host ">>> 3. 部署到 Kubernetes" -ForegroundColor White

$kustomizeDir = "$projectRoot/deploy/k8s/overlays/local"
Write-Host "  使用配置: $kustomizeDir" -ForegroundColor Gray

kubectl apply -k $kustomizeDir 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] kubectl apply 失败" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] 资源已提交" -ForegroundColor Green

# ── 等待就绪 ────────────────────────────────────────────

Write-Host ""
Write-Host ">>> 4. 等待服务就绪（最多 120 秒）" -ForegroundColor White

$timeout = 120
$elapsed = 0
$interval = 5

:waitLoop while ($elapsed -lt $timeout) {
    $pods = kubectl get pods -n $namespace -o json 2>&1 | ConvertFrom-Json
    $totalPods = $pods.items.Count
    $readyPods = ($pods.items | Where-Object { $_.status.phase -eq "Running" -and $_.status.containerStatuses[0].ready }).Count

    Write-Host "  [$elapsed s] Pods: $readyPods/$totalPods Running" -ForegroundColor Gray

    if ($readyPods -eq $totalPods -and $totalPods -gt 0) {
        Write-Host "  [OK] 所有 Pod 就绪" -ForegroundColor Green
        break waitLoop
    }

    # 检查异常
    $failed = $pods.items | Where-Object { $_.status.phase -eq "Failed" -or $_.status.phase -eq "CrashLoopBackOff" }
    if ($failed) {
        Write-Host "  [FAIL] 检测到异常 Pod:" -ForegroundColor Red
        foreach ($f in $failed) {
            Write-Host "    - $($f.metadata.name): $($f.status.phase)" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "  查看日志: kubectl logs -n $namespace $($failed[0].metadata.name)" -ForegroundColor Yellow
        break waitLoop
    }

    Start-Sleep -Seconds $interval
    $elapsed += $interval
}

# ── 端口转发 ────────────────────────────────────────────

Write-Host ""
Write-Host ">>> 5. 启动端口转发" -ForegroundColor White

Write-Host "  后端 API:  http://localhost:$BackendPort" -ForegroundColor White
Write-Host "  前端:      http://localhost:$FrontendPort" -ForegroundColor White
Write-Host ""

$backendJob = Start-Job -Name "port-fwd-backend" -ScriptBlock {
    param($ns, $port)
    kubectl port-forward -n $ns svc/backend $port`:8000 2>&1 | Out-Null
} -ArgumentList $namespace, $BackendPort

$frontendJob = Start-Job -Name "port-fwd-frontend" -ScriptBlock {
    param($ns, $port)
    kubectl port-forward -n $ns svc/frontend $port`:80 2>&1 | Out-Null
} -ArgumentList $namespace, $FrontendPort

Start-Sleep -Seconds 2

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  部署完成！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 健康检查
try {
    $health = Invoke-RestMethod -Uri "http://localhost:$BackendPort/health" -Method Get -TimeoutSec 5
    Write-Host "  后端健康检查: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "  后端健康检查: 等待中..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  按 Ctrl+C 停止端口转发，或执行:" -ForegroundColor Gray
Write-Host "    Stop-Job -Name 'port-fwd-*'" -ForegroundColor Gray
Write-Host "    kubectl delete namespace ai-diagnostic" -ForegroundColor Gray
Write-Host ""

# ── 保持运行 ────────────────────────────────────────────
try {
    while ($true) {
        Start-Sleep -Seconds 10
        # 检查 job 是否还在运行
        if ((Get-Job -Name "port-fwd-backend" -ErrorAction SilentlyContinue).State -ne "Running") {
            Write-Host "  后端端口转发已停止" -ForegroundColor Yellow
            break
        }
    }
} finally {
    Get-Job -Name "port-fwd-*" | Stop-Job -ErrorAction SilentlyContinue
    Get-Job -Name "port-fwd-*" | Remove-Job -ErrorAction SilentlyContinue
}
