@echo off

REM Explicit python path
set PYTHON_EXE="C:\Users\willb\AppData\Local\Programs\Python\Python310\python.exe"

REM Ensure consistent working dir
cd /d "C:\Users\willb\Documents\Scripts"

echo [1/4] Building journal_daily.csv ...
%PYTHON_EXE% "C:\Users\willb\Documents\Scripts\obsidian_journal_dataset.py"

timeout /t 3 >nul

echo [2/4] Building journal_meals.csv (nutrition + DeepSeek) ...
%PYTHON_EXE% "C:\Users\willb\Documents\Scripts\obsidian_build_meal_nutrition.py"

timeout /t 3 >nul

echo [3/4] Building Life Summary dashboard ...
%PYTHON_EXE% "C:\Users\willb\Documents\Scripts\obsidian_summarize_journal.py"

timeout /t 3 >nul

echo [4/4] Running Obsidian autotag ...
%PYTHON_EXE% ^
  "C:\Users\willb\Documents\Scripts\obsidian_autotag.py" ^
  "C:\Users\willb\Documents\Obsidian" ^
  --hours 24 ^
  >> "C:\Users\willb\Documents\Scripts\obsidian_autotag.log" 2>&1

echo Done.
