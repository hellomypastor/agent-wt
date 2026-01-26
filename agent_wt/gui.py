from __future__ import annotations

import argparse
from tkinter import messagebox, simpledialog, ttk
import tkinter as tk

from .config import get_worktree_entry, list_worktrees
from .core import (
    SUPPORTED_AGENTS,
    handle_commit,
    handle_create,
    handle_diff,
    handle_git,
    handle_open,
    handle_remove,
    handle_run,
    handle_set,
)
from .errors import UserError


def run_gui(ctx):
    root = tk.Tk()
    root.title("agent-wt")
    root.geometry("920x460")

    launch_var = tk.StringVar(root, value="spawn")
    allow_dirty_var = tk.BooleanVar(root, value=False)
    sandbox_var = tk.BooleanVar(root, value=False)
    no_sandbox_var = tk.BooleanVar(root, value=False)
    sandbox_no_network_var = tk.BooleanVar(root, value=False)
    sandbox_profile_var = tk.StringVar(root, value="")
    sandbox_write_var = tk.StringVar(root, value="")

    columns = ("name", "branch", "agent", "status", "dirty", "ahead", "behind", "path")
    tree = ttk.Treeview(root, columns=columns, show="headings")
    for col in columns:
        tree.heading(col, text=col)
        width = 80 if col in {"dirty", "ahead", "behind"} else 120
        if col == "path":
            width = 360
        tree.column(col, width=width, anchor="w")
    tree.pack(fill="both", expand=True, padx=8, pady=8)

    def refresh():
        tree.delete(*tree.get_children())
        for item in list_worktrees(ctx):
            tree.insert("", "end", iid=item["name"], values=[item[col] for col in columns])

    def run_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree to run.")
            return
        name = sel[0]
        write_paths = [item.strip() for item in sandbox_write_var.get().split(",") if item.strip()]
        try:
            handle_run(
                argparse.Namespace(
                    name=name,
                    agent=None,
                    cmd=None,
                    wait=False,
                    launch=launch_var.get(),
                    allow_dirty=allow_dirty_var.get(),
                    sandbox=sandbox_var.get(),
                    no_sandbox=no_sandbox_var.get(),
                    sandbox_profile=sandbox_profile_var.get().strip() or None,
                    sandbox_write=write_paths or None,
                    sandbox_no_network=sandbox_no_network_var.get(),
                    sandbox_network=False,
                ),
                ctx,
            )
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    def remove_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree to remove.")
            return
        name = sel[0]
        if not messagebox.askyesno("agent-wt", f'Untrack "{name}"? (no path/branch deletion)'):
            return
        try:
            handle_remove(
                argparse.Namespace(name=name, delete_path=False, delete_branch=False, prune=False, force=False),
                ctx,
            )
            refresh()
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    def open_selected(app):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree to open.")
            return
        name = sel[0]
        try:
            handle_open(argparse.Namespace(name=name, launch=app), ctx)
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    def git_status():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree.")
            return
        name = sel[0]
        try:
            handle_git(argparse.Namespace(name=name, git_args=["status"]), ctx)
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    def git_diff():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree.")
            return
        name = sel[0]
        try:
            handle_diff(argparse.Namespace(name=name, git_args=[]), ctx)
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    def git_push():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree.")
            return
        name = sel[0]
        try:
            handle_open  # noqa: B018
            from .core import handle_push  # local import to avoid cycles
            handle_push(argparse.Namespace(name=name, remote="origin", branch=None), ctx)
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    def git_commit():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree.")
            return
        name = sel[0]
        msg = simpledialog.askstring("agent-wt", f'Commit message for "{name}":')
        if msg is None:
            return
        try:
            handle_commit(argparse.Namespace(name=name, message=msg, all=True), ctx)
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    def open_create_dialog():
        dialog = tk.Toplevel(root)
        dialog.title("Create worktree")
        dialog.geometry("420x320")

        labels = ["Name", "Agent", "Base", "Branch", "Path", "Command"]
        defaults = {
            "Agent": "codex",
            "Base": "main",
            "Branch": "",
            "Path": "",
            "Command": "",
        }
        entries = {}
        for idx, label in enumerate(labels):
            tk.Label(dialog, text=label).grid(row=idx, column=0, sticky="w", padx=8, pady=4)
            if label == "Agent":
                agent_var = tk.StringVar(dialog, defaults[label])
                widget = ttk.Combobox(dialog, textvariable=agent_var, values=SUPPORTED_AGENTS, state="readonly")
                widget.grid(row=idx, column=1, sticky="we", padx=8, pady=4)
                entries[label] = widget
            else:
                entry = tk.Entry(dialog)
                entry.insert(0, defaults.get(label, ""))
                entry.grid(row=idx, column=1, sticky="we", padx=8, pady=4)
                entries[label] = entry
        dialog.columnconfigure(1, weight=1)

        def on_create(start_after=False):
            name_val = entries["Name"].get().strip()
            if not name_val:
                messagebox.showerror("agent-wt", "Name is required.")
                return
            write_paths = [item.strip() for item in sandbox_write_var.get().split(",") if item.strip()]
            ns = argparse.Namespace(
                name=name_val,
                agent=entries["Agent"].get().strip() or "codex",
                base=entries["Base"].get().strip() or "main",
                branch=entries["Branch"].get().strip() or None,
                path=entries["Path"].get().strip() or None,
                cmd=entries["Command"].get().strip() or None,
                start=start_after,
                allow_dirty=allow_dirty_var.get(),
                use_existing_branch=False,
                launch=launch_var.get(),
                sandbox=sandbox_var.get(),
                no_sandbox=no_sandbox_var.get(),
                sandbox_profile=sandbox_profile_var.get().strip() or None,
                sandbox_write=write_paths or None,
                sandbox_no_network=sandbox_no_network_var.get(),
                sandbox_network=False,
            )
            try:
                handle_create(ns, ctx)
                refresh()
                if start_after:
                    try:
                        handle_run(
                            argparse.Namespace(
                                name=name_val,
                                agent=ns.agent,
                                cmd=ns.cmd,
                                wait=False,
                                launch=launch_var.get(),
                                allow_dirty=allow_dirty_var.get(),
                            ),
                            ctx,
                        )
                    except UserError as exc:  # noqa: BLE001
                        messagebox.showerror("agent-wt", f"Created, but failed to start: {exc}")
                dialog.destroy()
            except UserError as exc:
                messagebox.showerror("agent-wt", str(exc))

        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=len(labels), column=0, columnspan=2, pady=12)
        tk.Button(btn_frame, text="Create", command=lambda: on_create(False)).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Create & Start", command=lambda: on_create(True)).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=4)

    def edit_command():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("agent-wt", "Select a worktree to edit.")
            return
        name = sel[0]
        current = get_worktree_entry(ctx, name).get("command", "")
        new_cmd = simpledialog.askstring("agent-wt", f'New command for "{name}":', initialvalue=current)
        if new_cmd is None:
            return
        try:
            handle_set(argparse.Namespace(name=name, agent=None, cmd=new_cmd, path=None), ctx)
            refresh()
        except UserError as exc:
            messagebox.showerror("agent-wt", str(exc))

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=8, pady=4)
    tk.Label(btns, text="Launch via:").pack(side="left", padx=4)
    ttk.Combobox(
        btns,
        textvariable=launch_var,
        values=["spawn", "terminal", "iterm"],
        state="readonly",
        width=10,
    ).pack(side="left", padx=4)
    tk.Checkbutton(btns, text="Allow dirty", variable=allow_dirty_var).pack(side="left", padx=4)
    tk.Checkbutton(btns, text="Sandbox", variable=sandbox_var).pack(side="left", padx=4)
    tk.Checkbutton(btns, text="No sandbox", variable=no_sandbox_var).pack(side="left", padx=4)
    tk.Checkbutton(btns, text="No network", variable=sandbox_no_network_var).pack(side="left", padx=4)
    tk.Label(btns, text="Profile").pack(side="left", padx=4)
    tk.Entry(btns, textvariable=sandbox_profile_var, width=16).pack(side="left", padx=4)
    tk.Label(btns, text="Write paths").pack(side="left", padx=4)
    tk.Entry(btns, textvariable=sandbox_write_var, width=18).pack(side="left", padx=4)
    tk.Button(btns, text="Refresh", command=refresh).pack(side="left", padx=4)
    tk.Button(btns, text="Run Selected", command=run_selected).pack(side="left", padx=4)
    tk.Button(btns, text="Create...", command=open_create_dialog).pack(side="left", padx=4)
    tk.Button(btns, text="Edit Command", command=edit_command).pack(side="left", padx=4)
    tk.Button(btns, text="Untrack", command=remove_selected).pack(side="left", padx=4)
    tk.Button(btns, text="Open Terminal", command=lambda: open_selected("terminal")).pack(side="left", padx=4)
    tk.Button(btns, text="Open iTerm", command=lambda: open_selected("iterm")).pack(side="left", padx=4)
    tk.Button(btns, text="Git Status", command=git_status).pack(side="left", padx=4)
    tk.Button(btns, text="Git Diff", command=git_diff).pack(side="left", padx=4)
    tk.Button(btns, text="Git Commit", command=git_commit).pack(side="left", padx=4)
    tk.Button(btns, text="Git Push", command=git_push).pack(side="left", padx=4)

    refresh()
    root.mainloop()
