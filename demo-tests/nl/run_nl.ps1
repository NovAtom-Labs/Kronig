param([string[]]$Names, [int]$Deadline = 5400)
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
$env:OPENHANDS_SUPPRESS_BANNER='1'; $env:PYTHONUTF8='1'; $env:TCAD_BACKEND='sentaurus'
$k='C:\Development\NovAtom Labs\Kronig'; $d="$k\demo-tests\nl"; Set-Location $k
foreach($n in ($Names -split ',' | ? { $_ })){
  $run="$d\runs\$n"; if(Test-Path $run){ Remove-Item $run -Recurse -Force }; New-Item -ItemType Directory "$run\in" | Out-Null
  & "$k\.venv\Scripts\python.exe" -I -c "import sys,json; sys.path.insert(0, r'$d'); from catalog import TESTS; t=TESTS['$n']; open(r'$run\in\prompt.md','w',encoding='utf-8').write(t['prompt']); json.dump({'*': t['facts']}, open(r'$run\in\answers.json','w',encoding='utf-8'))"
  $t=Get-Date
  & "$k\.venv\Scripts\python.exe" "$d\drive.py" --prompt "$run\in\prompt.md" --answers "$run\in\answers.json" --output "$run\out" --deadline $Deadline > "$run\drive.log" 2>&1
  & "$k\.venv\Scripts\python.exe" "$d\check.py" $run $n > "$run\check.txt" 2>&1
  "$n done seconds=$([int]((Get-Date)-$t).TotalSeconds) :: $((Get-Content "$run\check.txt" -TotalCount 1))" | Add-Content "$d\_nl_progress.txt"
}