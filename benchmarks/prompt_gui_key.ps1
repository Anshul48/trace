Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Trace: Secure Sail Research Key Entry"
$form.Size = New-Object System.Drawing.Size(520, 220)
$form.StartPosition = "CenterScreen"
$form.TopMost = $true
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.MinimizeBox = $false

$iconLabel = New-Object System.Windows.Forms.Label
$iconLabel.Location = New-Object System.Drawing.Point(20, 20)
$iconLabel.Size = New-Object System.Drawing.Size(460, 35)
$iconLabel.Text = "Paste your Sail Research API Key below.`nInput is masked (never echoed in chat or logs):"
$iconLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$form.Controls.Add($iconLabel)

$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Location = New-Object System.Drawing.Point(20, 65)
$textBox.Size = New-Object System.Drawing.Size(460, 26)
$textBox.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$textBox.UseSystemPasswordChar = $true
$form.Controls.Add($textBox)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Location = New-Object System.Drawing.Point(20, 100)
$statusLabel.Size = New-Object System.Drawing.Size(460, 20)
$statusLabel.ForeColor = [System.Drawing.Color]::DarkBlue
$statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$form.Controls.Add($statusLabel)

$okButton = New-Object System.Windows.Forms.Button
$okButton.Location = New-Object System.Drawing.Point(250, 130)
$okButton.Size = New-Object System.Drawing.Size(120, 32)
$okButton.Text = "Save & Validate"
$okButton.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$form.Controls.Add($okButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Location = New-Object System.Drawing.Point(380, 130)
$cancelButton.Size = New-Object System.Drawing.Size(100, 32)
$cancelButton.Text = "Cancel"
$cancelButton.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($cancelButton)

$okButton.Add_Click({
    $key = $textBox.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($key)) {
        [System.Windows.Forms.MessageBox]::Show("Please enter a valid API key.", "Input Required", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
        return
    }

    $statusLabel.Text = "Validating key against https://api.sailresearch.com/v1/models..."
    $form.Refresh()

    # Pre-flight check via Python client
    $verifyScript = @"
import sys
from benchmarks.run_deepseek_flash_bakeoff import SailResearchClient
client = SailResearchClient(api_key='$key')
ok, msg = client.verify_credentials()
print(f'{ok}|{msg}')
sys.exit(0 if ok else 1)
"@
    $proc = Start-Process -FilePath "python" -ArgumentList "-c", "`"$verifyScript`"" -NoNewWindow -PassThru -Wait -RedirectStandardOutput "key_val.tmp"
    $valOutput = Get-Content "key_val.tmp" -ErrorAction SilentlyContinue
    Remove-Item "key_val.tmp" -ErrorAction SilentlyContinue

    $isValid = ($proc.ExitCode -eq 0)
    if (-not $isValid) {
        $diagMsg = if ($valOutput) { $valOutput } else { "HTTP 401/403 or network error" }
        $res = [System.Windows.Forms.MessageBox]::Show("Key validation returned: $diagMsg`n`nSave key anyway?", "Validation Warning", [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Question)
        if ($res -ne [System.Windows.Forms.DialogResult]::Yes) {
            $statusLabel.Text = "Key entry discarded."
            return
        }
    }

    # Save to .env
    $envPath = ".env"
    $lines = @()
    $found = $false
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            if ($_ -like "SAIL_API_KEY=*") {
                $lines += "SAIL_API_KEY=$key"
                $found = $true
            } else {
                $lines += $_
            }
        }
    }
    if (-not $found) {
        $lines += "SAIL_API_KEY=$key"
    }
    $lines | Set-Content $envPath -Encoding UTF8

    [System.Windows.Forms.MessageBox]::Show("SAIL_API_KEY successfully saved to .env!`nYou can close this dialog.", "Success", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
    $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Close()
})

$form.AcceptButton = $okButton
$form.CancelButton = $cancelButton

$res = $form.ShowDialog()
if ($res -eq [System.Windows.Forms.DialogResult]::OK) {
    exit 0
} else {
    exit 1
}
