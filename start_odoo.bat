@echo off
cd /d "%~dp0"
call virtual\Scripts\activate.bat
python odoo-bin -c debian\odoo.conf -d odoo19 %*
