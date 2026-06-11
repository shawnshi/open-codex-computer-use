param()

$ErrorActionPreference = "Stop"
Write-Host ">>> Sprint 5: UIAccess Manifest & Code Signing Pipeline <<<"

# 1. Ensure rsrc is installed
Write-Host "Installing rsrc..."
go install github.com/akavel/rsrc@latest
$env:PATH += ";$env:USERPROFILE\go\bin"

# 2. Build the Manifest Syso
Write-Host "Packing main.manifest into syso..."
rsrc -manifest main.manifest -o rsrc.syso

# 3. Build the Go Binary
Write-Host "Building Go binary..."
go build -ldflags="-s -w" -o open-computer-use.exe main.go

# 4. Digital Signing (Requires Elevation to trust root)
Write-Host "Setting up local Code Signing Certificate..."
$certSubject = "CN=AntigravityLocalSigner"
$cert = Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -eq $certSubject } | Select-Object -First 1

if (-not $cert) {
    Write-Host "Creating new Self-Signed Code Signing Certificate..."
    # Needs Admin
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $certSubject -CertStoreLocation Cert:\LocalMachine\My
    
    Write-Host "Trusting the certificate (Adding to Root store)..."
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store "Root", "LocalMachine"
    $store.Open("ReadWrite")
    $store.Add($cert)
    $store.Close()
} else {
    Write-Host "Found existing certificate."
}

Write-Host "Signing the executable..."
Set-AuthenticodeSignature -Certificate $cert -FilePath ".\open-computer-use.exe"

Write-Host ""
Write-Host "========================================================="
Write-Host "SUCCESS: open-computer-use.exe is now built with uiAccess=true and signed!"
Write-Host "IMPORTANT: To bypass UIPI, you MUST move this .exe to a secure location (e.g. C:\Program Files\OpenComputerUse) and run it from there."
Write-Host "========================================================="
