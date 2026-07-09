$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Stop any stale Odoo instance still bound to port 8069.
Get-NetTCPConnection -LocalPort 8069 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }

& "$Root\virtual\Scripts\Activate.ps1"
python odoo-bin -c "$Root\debian\odoo.conf" -d odoo19 @args
