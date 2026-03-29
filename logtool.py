import platform
import os
import subprocess
import json
import argparse
from pathlib import Path
from datetime import datetime

class LogExtractor:
	def __init__(self):
		self.os_type = platform.system()
		self.home = str(Path.home())

	def get_all_data(self, limit=20, keyword=None):
		"""Main entry point to collect logs based on OS."""
		data = {
			"metadata": {
				"timestamp": datetime.now().isoformat(),
				"os": self.os_type,
				"user": os.getlogin() if self.os_type != "Windows" else os.getenv('USERNAME'),
				"filter_keyword": keyword if keyword else "None"
			},
			"logs": {}
		}

		if self.os_type == "Windows":
			data["logs"] = self._windows_logs(limit, keyword)
		else:
			data["logs"] = self._unix_logs(limit, keyword)
			
		return data

	def _apply_filter(self, line, keyword):
		"""Helper to check if keyword exists in a string (case-insensitive)."""
		if not keyword:
			return True
		return keyword.lower() in str(line).lower()

	def _windows_logs(self, limit, keyword):
		logs = {}
		# 1. System Event Logs
		try:
			import win32evtlog
			handle = win32evtlog.OpenEventLog(None, 'System')
			flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
			events = win32evtlog.ReadEventLog(handle, flags, 0)
			
			win_events = []
			for e in events:
				if len(win_events) >= limit:
					break
				# Basic event data
				entry = {"source": e.SourceName, "time": str(e.TimeGenerated), "id": e.EventID}
				if self._apply_filter(entry, keyword):
					win_events.append(entry)
			logs['windows_event_system'] = win_events
		except Exception as e:
			logs['windows_event_system'] = f"Error accessing EventLog: {e}"

		# 2. PowerShell History
		ps_path = os.path.join(os.getenv('APPDATA', ''), r"Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt")
		logs['powershell_history'] = self._read_last_lines(ps_path, limit, keyword)
		return logs

	def _unix_logs(self, limit, keyword):
		logs = {}
		# 1. System Logs via journalctl
		try:
			# We fetch more lines than limit initially to allow for filtering
			cmd = ['journalctl', '-n', str(limit * 5), '--output', 'json']
			res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
			entries = [json.loads(line) for line in res.decode().splitlines() if line]
			
			filtered_entries = [e for e in entries if self._apply_filter(e, keyword)][:limit]
			logs['system_journal'] = filtered_entries
		except:
			alt_log = "/var/log/syslog" if self.os_type == "Linux" else "/var/log/system.log"
			logs['system_file'] = self._read_last_lines(alt_log, limit, keyword)

		# 2. Terminal History (bash/zsh)
		for shell in ['.bash_history', '.zsh_history']:
			path = os.path.join(self.home, shell)
			if os.path.exists(path):
				logs[f'terminal_{shell.strip(".")}'] = self._read_last_lines(path, limit, keyword)
		return logs

	def _read_last_lines(self, path, count, keyword):
		if not os.path.exists(path): 
			return "Log file not found"
		try:
			filtered_lines = []
			with open(path, 'r', encoding='utf-8', errors='ignore') as f:
				lines = f.readlines()
				# Iterate backwards to find most recent matches
				for line in reversed(lines):
					if len(filtered_lines) >= count:
						break
					clean_line = line.strip()
					if self._apply_filter(clean_line, keyword):
						filtered_lines.append(clean_line)
			return filtered_lines
		except Exception as e:
			return f"Read error: {e}"

	def save_json(self, data, filename):
		with open(filename, 'w', encoding='utf-8') as f:
			json.dump(data, f, ensure_ascii=False, indent=4)

	def save_txt(self, data, filename):
		with open(filename, 'w', encoding='utf-8') as f:
			f.write(f"SYSTEM LOG REPORT - Generated on: {data['metadata']['timestamp']}\n")
			f.write(f"OS: {data['metadata']['os']} | User: {data['metadata']['user']}\n")
			f.write(f"Filter Keyword: {data['metadata']['filter_keyword']}\n")
			f.write("="*60 + "\n\n")
			
			for category, content in data['logs'].items():
				f.write(f"--- CATEGORY: {category.upper()} ---\n")
				if isinstance(content, list):
					if not content:
						f.write("No entries found matching criteria.\n")
					for entry in content:
						f.write(f"{entry}\n")
				else:
					f.write(f"{content}\n")
				f.write("\n")

def main():
	parser = argparse.ArgumentParser(description="Multi-platform System Log Extractor")
		
	parser.add_argument("-f", "--format", choices=["json", "txt"], default="json", 
						help="Output file format (default: json)")
	parser.add_argument("-o", "--output", default="log_report", 
						help="Output filename without extension (default: log_report)")
	parser.add_argument("-l", "--limit", type=int, default=20, 
						help="Number of log entries to retrieve (default: 20)")
	parser.add_argument("-k", "--keyword", default=None, 
						help="Filter logs by a specific keyword (case-insensitive)")

	args = parser.parse_args()
		
	extractor = LogExtractor()
	print(f"[*] Initializing log collection for {extractor.os_type}...")
	if args.keyword:
		print(f"[*] Applying filter: '{args.keyword}'")
		
	data = extractor.get_all_data(limit=args.limit, keyword=args.keyword)
	full_filename = f"{args.output}.{args.format}"
		
	if args.format == "json":
		extractor.save_json(data, full_filename)
	else:
		extractor.save_txt(data, full_filename)
		
	print(f"[SUCCESS] Logs saved to: {full_filename}")

if __name__ == "__main__":
	main()
