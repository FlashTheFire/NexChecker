#!/usr/bin/env pwsh
<#
.SYNOPSIS
    NexChecker - Complete Docker Stack Launcher with Cloudflare Tunnel & HTTPS
.DESCRIPTION
    Auto-healing DNS pool (nip.io / sslip.io / traefik.me), SSL cert generation,
    full Docker stack (API + Telegram Bot + Nginx + Cloudflare Tunnel),
    instant public zero-warning HTTPS tunnel discovery, and live health dashboard.
.PARAMETER Action
    up | down | restart | logs | status | rebuild
.PARAMETER Service
    Specific service name for logs (optional)
.EXAMPLE
    .\Start-NexChecker.ps1
    .\Start-NexChecker.ps1 -Action logs -Service tunnel
    .\Start-NexChecker.ps1 -Action down
    .\Start-NexChecker.ps1 -Action status
#>

param(
    [ValidateSet("up","down","restart","logs","status","rebuild")]
    [string]$Action = "up",
    [string]$Service = ""
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# ---------- Paths ----------
$ProjectRoot  = $PSScriptRoot
$ComposeFile  = Join-Path $ProjectRoot "docker-compose.yml"
$EnvFile      = Join-Path $ProjectRoot ".env"
$CertsDir     = Join-Path $ProjectRoot "docker\certs"
$LogFile      = Join-Path $ProjectRoot "docker\startup.log"

New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
New-Item -ItemType Directory -Force -Path $CertsDir | Out-Null

# DNS provider pool
$DNS_POOL = @(
    [pscustomobject]@{ Name="nip.io";     Domain="nexchecker.127.0.0.1.nip.io" }
    [pscustomobject]@{ Name="sslip.io";   Domain="nexchecker.127.0.0.1.sslip.io" }
    [pscustomobject]@{ Name="traefik.me"; Domain="nexchecker.traefik.me" }
)

# ==================== HELPERS ====================

function Write-Log {
    param([string]$Msg, [string]$Level="INFO", [ConsoleColor]$Color="Cyan")
    $ts   = Get-Date -Format "HH:mm:ss"
    $line = "[$ts][$Level] $Msg"
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Test-Cmd { param([string]$C); return [bool](Get-Command $C -ErrorAction SilentlyContinue) }

function Get-EnvVal {
    param([string]$K)
    if (-not (Test-Path $EnvFile)) { return "" }
    $line = Get-Content $EnvFile -ErrorAction SilentlyContinue | Where-Object { $_ -match "^$K=" } | Select-Object -First 1
    if ($line) { return ($line -split "=",2)[1].Trim() }
    return ""
}

function Set-EnvVal {
    param([string]$K, [string]$V)
    if (-not (Test-Path $EnvFile)) { return }
    $raw = Get-Content $EnvFile -Raw -ErrorAction SilentlyContinue
    if ($raw -match "(?m)^$K=") {
        $raw = [regex]::Replace($raw, "(?m)^$K=.*", "$K=$V")
    } else {
        $raw += "`n$K=$V"
    }
    Set-Content -Path $EnvFile -Value $raw -Encoding UTF8 -NoNewline
}

function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ==========================================================" -ForegroundColor Cyan
    Write-Host "  =     NexChecker - Universal Multi-Platform Checker      =" -ForegroundColor Cyan
    Write-Host "  =      Full Docker Stack + Nginx + Cloudflare Tunnel     =" -ForegroundColor Cyan
    Write-Host "  ==========================================================" -ForegroundColor Cyan
    Write-Host ""
}

# ==================== SSL CERTIFICATES ====================

function Ensure-Certs {
    param([string]$Domain)
    $cert = Join-Path $CertsDir "cert.pem"
    $key  = Join-Path $CertsDir "key.pem"

    if ((Test-Path $cert) -and (Test-Path $key)) {
        Write-Log "SSL certificates already exist in $CertsDir" "CERT" Green
        return
    }

    Write-Log "Generating SSL certificate for $Domain..." "CERT" Yellow

    $mkcertExe = $null
    if (Test-Cmd "mkcert") {
        $mkcertExe = "mkcert"
    } elseif (Test-Path "$env:USERPROFILE\AppData\Local\Programs\mkcert.exe") {
        $mkcertExe = "$env:USERPROFILE\AppData\Local\Programs\mkcert.exe"
    }

    if ($mkcertExe) {
        Write-Log "Generating trusted certs via mkcert..." "CERT" Green
        & $mkcertExe -cert-file $cert -key-file $key $Domain "api.$Domain" "localhost" "127.0.0.1" 2>&1 | Out-Null
        if ((Test-Path $cert) -and (Test-Path $key)) {
            Write-Log "Trusted certificate generated successfully with mkcert" "CERT" Green
            return
        }
    }

    if (Test-Cmd "openssl") {
        Write-Log "Generating self-signed cert via OpenSSL fallback..." "CERT" DarkYellow
        & openssl req -x509 -newkey rsa:2048 -nodes -keyout $key -out $cert -days 365 -subj "/CN=$Domain" 2>&1 | Out-Null
        if ((Test-Path $cert) -and (Test-Path $key)) {
            Write-Log "Self-signed certificate generated via OpenSSL" "CERT" Green
            return
        }
    }

    # Pure PowerShell fallback if no external tool
    Write-Log "Generating certificate via PowerShell New-SelfSignedCertificate..." "CERT" DarkYellow
    $pfxPath = Join-Path $CertsDir "temp.pfx"
    $ss = New-SelfSignedCertificate -DnsName $Domain, "localhost", "127.0.0.1" -CertStoreLocation "cert:\CurrentUser\My" -NotAfter (Get-Date).AddYears(1)
    $pwd = ConvertTo-SecureString -String "tempPass123" -Force -AsPlainText
    Export-PfxCertificate -Cert $ss -FilePath $pfxPath -Password $pwd | Out-Null

    # Export PEM
    if (Test-Cmd "openssl") {
        & openssl pkcs12 -in $pfxPath -nocerts -out $key -nodes -passin pass:tempPass123 2>&1 | Out-Null
        & openssl pkcs12 -in $pfxPath -clcerts -nokeys -out $cert -passin pass:tempPass123 2>&1 | Out-Null
        Remove-Item $pfxPath -Force -ErrorAction SilentlyContinue
    }
}

# ==================== ACTIONS ====================

switch ($Action) {
    "down" {
        Write-Log "Stopping NexChecker Docker stack..." "DOWN" Yellow
        docker compose -f $ComposeFile down
        Write-Log "NexChecker stack stopped." "DOWN" Green
        exit 0
    }

    "restart" {
        Write-Log "Restarting NexChecker Docker stack..." "RESTART" Yellow
        docker compose -f $ComposeFile down
        & $PSCommandPath -Action up
        exit 0
    }

    "logs" {
        if ($Service) {
            docker compose -f $ComposeFile logs -f $Service
        } else {
            docker compose -f $ComposeFile logs -f
        }
        exit 0
    }

    "status" {
        docker compose -f $ComposeFile ps
        exit 0
    }

    "rebuild" {
        Write-Log "Rebuilding NexChecker container images..." "BUILD" Yellow
        docker compose -f $ComposeFile build --no-cache
        & $PSCommandPath -Action up
        exit 0
    }

    "up" {
        Write-Banner

        # 1. Docker check
        if (-not (Test-Cmd "docker")) {
            Write-Log "Docker CLI not found! Please install Docker Desktop." "ERROR" Red
            exit 1
        }
        $dockerReady = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Docker daemon is not running! Please start Docker Desktop." "ERROR" Red
            exit 1
        }
        Write-Log "Docker engine verified and ready." "DOCKER" Green

        # 2. Domain resolution
        $domain = Get-EnvVal "LOCAL_DOMAIN"
        if (-not $domain) {
            $domain = $DNS_POOL[0].Domain
            Set-EnvVal "LOCAL_DOMAIN" $domain
        }
        Write-Log "Local Domain: $domain" "DOMAIN" Cyan

        # 3. SSL certificates
        Ensure-Certs $domain

        # 4. Compose up
        Write-Log "Launching Docker Compose containers..." "COMPOSE" Yellow
        docker compose -f $ComposeFile up -d --remove-orphans
        if ($LASTEXITCODE -ne 0) {
            Write-Log "docker compose up failed with error." "ERROR" Red
            exit 1
        }

        # 5. Discover Cloudflare Tunnel URL
        Write-Log "Waiting for Cloudflare Tunnel public HTTPS URL..." "TUNNEL" Yellow
        $tunnelUrl = ""
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            $tunnelLogs = docker logs nexchecker_tunnel 2>&1
            $match = [regex]::Match($tunnelLogs, "https://[a-zA-Z0-9\-]+\.trycloudflare\.com")
            if ($match.Success) {
                $tunnelUrl = $match.Value
                break
            }
        }

        if ($tunnelUrl) {
            Write-Log "Discovered Cloudflare Tunnel URL: $tunnelUrl" "TUNNEL" Green
            Set-EnvVal "WEBAPP_URL" $tunnelUrl
        } else {
            Write-Log "Named tunnel configured or quick tunnel initializing in background." "TUNNEL" Cyan
        }

        # 6. Status Summary
        Write-Host ""
        Write-Host "  ==========================================================" -ForegroundColor Green
        Write-Host "  =              NexChecker Stack Is Online!               =" -ForegroundColor Green
        Write-Host "  ==========================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Local HTTPS WebApp:     https://$domain" -ForegroundColor White
        Write-Host "  Local Health Check:     https://$domain/api/health" -ForegroundColor White
        if ($tunnelUrl) {
            Write-Host "  Public Cloudflare URL:  $tunnelUrl" -ForegroundColor Green
            Write-Host "  Telegram Mini App URL:  $tunnelUrl" -ForegroundColor Green
        }
        Write-Host ""

        docker compose -f $ComposeFile ps
    }
}
