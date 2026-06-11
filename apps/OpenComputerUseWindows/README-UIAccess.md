# 穿透 Windows UIPI 权限壁垒指南 (UIAccess)

在 Sprint 5 中，我们已经通过 `main.manifest` 将 Go 核心引擎编译为了具备 `uiAccess="true"` 提权声明的版本。
这使得 Agent 能够**越过普通权限沙盒，穿透 UIPI (User Interface Privilege Isolation)**，直接操作那些运行在“管理员权限”下的应用（例如任务管理器、注册表编辑器、安装程序，甚至杀毒软件的界面）。

## 激活要求

由于 Windows 的硬性安全策略，仅仅在 manifest 中声明 `uiAccess="true"` 是不够的，必须满足以下两个物理条件：
1. **数字签名**：程序必须被受系统信任的代码签名证书（Code Signing Certificate）签名。
2. **安全位置**：程序必须放置在受系统保护的安全目录下，通常是 `C:\Program Files\` 或 `C:\Program Files (x86)\`。

## 激活步骤

请您在拥有管理员权限的 PowerShell (Run as Administrator) 中执行以下命令，完成自我签名：

```powershell
# 1. 导入安全模块
Import-Module Microsoft.PowerShell.Security

# 2. 生成本地自签名的代码签名证书
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=OpenComputerUseLocalSigner" -CertStoreLocation Cert:\LocalMachine\My

# 3. 将证书添加到系统的受信任根证书颁发机构中 (这步可能会弹窗要求确认，请点击“是”)
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store "Root", "LocalMachine"
$store.Open("ReadWrite")
$store.Add($cert)
$store.Close()

# 4. 对生成的 open-computer-use.exe 进行数字签名
Set-AuthenticodeSignature -Certificate $cert -FilePath "C:\path\to\your\open-computer-use.exe"
```

## 部署与执行

签名成功后，请将该 `open-computer-use.exe` **剪切或复制到 `C:\Program Files\OpenComputerUse\` 目录下**。

随后，您只需要在您的 MCP Server 配置中将路径指向 `C:\Program Files\OpenComputerUse\open-computer-use.exe`。
至此，Agent 将获得真正的“上帝之眼”，所有管理员级别的弹窗和界面都将对 Agent 完全敞开大门！
