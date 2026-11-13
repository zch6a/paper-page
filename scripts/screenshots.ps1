# The README's images, from the made-up example, with headless Chrome (no network: every host but 127.0.0.1 unresolvable).
# Run from the repository: pwsh scripts/screenshots.ps1 (or Windows PowerShell). Chrome's path may differ on your machine.
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$page = "file:///$($PWD.Path.Replace('\','/'))/examples/tiny-fields/index.html"
$card = "file:///$($PWD.Path.Replace('\','/'))/scripts/social-card.html"
function Shot($url, $size, $file, $dark) {
    $a = @("--headless=new", "--no-proxy-server", '"--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"',
           "--user-data-dir=$env:TEMP\paper-page-shots-$([guid]::NewGuid())", "--hide-scrollbars", "--disable-gpu", "--no-first-run",
           "--virtual-time-budget=3000", "--window-size=$size", "--screenshot=$PWD\$file", $url)
    if ($dark) { $a = @("--force-dark-mode") + $a }
    Start-Process -Wait $chrome -ArgumentList $a
}
uv run paper-page render examples/tiny-fields
Shot $page "1100,1180" "docs\example-light.png" $false
Shot $page "1100,1180" "docs\example-dark.png" $true
Shot $card "1280,640" "docs\social-preview.png" $false
