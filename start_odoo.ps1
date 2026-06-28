$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
& "$Root\virtual\Scripts\Activate.ps1"
python odoo-bin -c "$Root\debian\odoo.conf" -d odoo19 @args
