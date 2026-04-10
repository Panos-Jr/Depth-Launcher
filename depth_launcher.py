"""
Depth Launcher
Polls a configurable server for status and auto-launches the game when ready.
"""

import json
import os
import subprocess
import sys
import time
import tkinter as tk
import threading
import urllib.request

POLL_INTERVAL = 3
CONFIG_FILE   = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.json")
DEFAULT_DOMAIN = "https://example.com"

STATE_COLOURS = {
    "idle":     "#4a9eff",
    "stopping": "#ff6b35",
    "starting": "#ffd23f",
    "waiting":  "#ffd23f",
    "ready":    "#06d6a0",
    "error":    "#ef476f",
    "unknown":  "#888888",
}


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"domain": DEFAULT_DOMAIN}


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def domain_to_status_url(domain: str) -> str:
    domain = domain.strip().rstrip("/")

    domain = domain.replace("http://", "").replace("https://", "")
    
    is_ip = all(c.isnumeric() for c in domain.split(":")[0].split("."))
    is_local = is_ip or domain.startswith("localhost")

    scheme = "http://" if is_local else "https://"
    
    return scheme + domain + "/status"



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Depth Launcher by Panos-Jr")
        self.resizable(False, False)
        self.configure(bg="#0d1117")
        self.geometry("360x300")
        self._center()

        self._icon_ref = tk.PhotoImage(
            file=os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "steering-wheel.png")
        )
        self.iconphoto(True, self._icon_ref)

        self._config     = load_config()
        self._status_url = domain_to_status_url(self._config.get("domain", DEFAULT_DOMAIN))

        self._watching_cycle = False
        self._launched       = False

        self._build_ui()
        self.after(500, self._schedule_poll)

    def _center(self):
        self.update_idletasks()
        w, h = 360, 300
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        pad = dict(padx=24)

        header_frame = tk.Frame(self, bg="#0d1117")
        header_frame.pack(fill="x", padx=24, pady=(20, 4))

        small_icon = self._icon_ref.subsample(20, 20)
        self._small_icon = small_icon

        tk.Label(header_frame, image=small_icon, bg="#0d1117").pack(side="left", padx=(0, 6))
        tk.Label(header_frame, text="DEPTH LAUNCHER", bg="#0d1117", fg="#7d8590",
                 font=("Courier", 10, "bold"), anchor="w").pack(side="left")

        self.state_var = tk.StringVar(value="connecting...")
        self.state_label = tk.Label(self, textvariable=self.state_var,
                                    bg="#0d1117", fg="#4a9eff",
                                    font=("Courier", 22, "bold"), anchor="w")
        self.state_label.pack(fill="x", **pad, pady=(0, 4))

        # Message
        self.msg_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.msg_var, bg="#0d1117", fg="#7d8590",
                 font=("Courier", 9), anchor="w", wraplength=312, justify="left"
                 ).pack(fill="x", **pad)

        # Timestamp
        self.time_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.time_var, bg="#0d1117", fg="#30363d",
                 font=("Courier", 8), anchor="w").pack(fill="x", **pad, pady=(4, 0))

        domain_frame = tk.Frame(self, bg="#0d1117")
        domain_frame.pack(fill="x", padx=24, pady=(14, 0))

        tk.Label(domain_frame, text="DOMAIN", bg="#0d1117", fg="#4a7a90",
                 font=("Courier", 10)).pack(anchor="w")

        inner = tk.Frame(domain_frame, bg="#0d1117")
        inner.pack(fill="x")

        self.domain_var = tk.StringVar(value=self._config.get("domain", DEFAULT_DOMAIN))
        self.domain_entry = tk.Entry(
            inner, textvariable=self.domain_var,
            bg="#0f1923", fg="#d0e8f0", insertbackground="#00c8ff",
            relief="flat", font=("Courier", 9),
            highlightthickness=1, highlightbackground="#1e3a4a",
            highlightcolor="#00c8ff",
        )
        self.domain_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))

        self.change_btn = tk.Button(
            inner, text="APPLY",
            bg="#0f1923", fg="#00c8ff",
            activebackground="#00c8ff", activeforeground="#000",
            relief="flat", font=("Courier", 8, "bold"),
            highlightthickness=1, highlightbackground="#1e3a4a",
            cursor="hand2", padx=8,
            command=self._apply_domain,
        )
        self.change_btn.pack(side="left", ipady=5)

        # Relaunch button (hidden by default)
        self.relaunch_btn = tk.Button(
            self, text="RELAUNCH",
            bg="#0f1923", fg="#06d6a0",
            activebackground="#06d6a0", activeforeground="#000",
            relief="flat", font=("Courier", 8, "bold"),
            highlightthickness=1, highlightbackground="#1e3a4a",
            cursor="hand2", padx=8,
            command=self._relaunch,
        )

        self.status_bar = tk.Frame(self, bg="#238636", height=4)
        self.status_bar.pack(fill="x", side="bottom")

    def _apply_domain(self):
        raw = self.domain_var.get().strip()
        if not raw:
            return
        self._status_url = domain_to_status_url(raw)
        self._config["domain"] = raw
        save_config(self._config)

        self._watching_cycle = False
        self._launched       = False
        self._set_state("unknown", f"Connecting to {self._status_url}...", "")
        self._schedule_poll()

    def _set_state(self, state: str, message: str = "", updated_at: str = ""):
        colour = STATE_COLOURS.get(state, STATE_COLOURS["unknown"])
        self.state_var.set(state.upper())
        self.state_label.configure(fg=colour)
        self.msg_var.set(message)
        self.time_var.set(f"updated {updated_at}" if updated_at else "")
        self.status_bar.configure(bg=colour)

        if state in ("idle", "ready"):
            self.relaunch_btn.pack(fill="x", padx=24, pady=(10, 0), ipady=5,
                                   before=self.status_bar)
        else:
            self.relaunch_btn.pack_forget()

    def _schedule_poll(self):
        threading.Thread(target=self._do_poll, daemon=True).start()

    def _do_poll(self):
        url = self._status_url
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            self.after(0, lambda: self._handle_poll_result(data))
        except Exception as e:
            self.after(0, lambda err=e: self._handle_poll_error(str(err)))

    def _handle_poll_result(self, data: dict):
        state   = data.get("state", "unknown")
        message = data.get("message", "")
        updated = data.get("updated_at", "")

        self._set_state(state, message, updated)

        if state in ("stopping", "starting", "waiting"):
            self._watching_cycle = True
            self._launched = False

        if state == "ready" and self._watching_cycle and not self._launched:
            self._launched = True
            self._watching_cycle = False
            self._launch_game()

        if state == "idle":
            self._watching_cycle = False
            self._launched = False

        self.after(POLL_INTERVAL * 1000, self._schedule_poll)

    def _handle_poll_error(self, error: str):
        self._set_state("unknown", f"Cannot reach server: {error}")
        self.after(POLL_INTERVAL * 1000, self._schedule_poll)

    def _relaunch(self):
        self._launched = False
        self.relaunch_btn.pack_forget()
        threading.Thread(target=self._do_launch, daemon=True).start()

    def _launch_game(self):
        self._set_state("ready", "🚀 Launching game...", "")
        threading.Thread(target=self._do_launch, daemon=True).start()

    def _do_launch(self):
        time.sleep(1)
        try:
            subprocess.run(["taskkill", "/f", "/im", "DepthGame.exe"], capture_output=True)
            time.sleep(1)

            server = self._status_url.replace("/status", "").strip()
            if server.startswith("https://"):
                server = server[len("https://"):]
            elif server.startswith("http://"):
                server = server[len("http://"):]

            server = server.split(":")[0]

            subprocess.Popen(
                [r".\Binaries\Win32\DepthGame.exe", server],
                cwd=os.path.dirname(os.path.abspath(sys.argv[0]))
            )
        except Exception as e:
            self.after(0, lambda err=e: self._set_state("error", f"Failed to launch game: {err}"))
            print(e)


if __name__ == "__main__":
    app = App()
    app.mainloop()