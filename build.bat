@echo off
pyinstaller --onefile --noconsole --name "DepthLauncher" --icon "steering-wheel.png" --add-data "steering-wheel.png;." depth_launcher.py
pause