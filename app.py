from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from updater_core import FileProposal, analyze, execute, suggested_backup_directory


class UpdaterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Atualizador de ficheiros")
        self.geometry("1250x650")
        self.minsize(950, 500)
        self.proposals: list[FileProposal] = []
        self.new_root = tk.StringVar()
        self.target_root = tk.StringVar()
        self.backup_root = tk.StringVar()
        self.update_name = tk.StringVar()
        self.summary = tk.StringVar(value="Nenhuma análise realizada.")
        self._build_ui()

    def _build_ui(self) -> None:
        paths = ttk.LabelFrame(self, text="Pastas")
        paths.pack(fill="x", padx=12, pady=10)
        self._path_row(paths, 0, "Ficheiros novos:", self.new_root, self._choose_new_root)
        self._path_row(paths, 1, "Pasta a atualizar:", self.target_root, self._choose_target_root)
        self._path_row(paths, 2, "Base dos obsoletos:", self.backup_root, self._choose_backup_root)

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(controls, text="Nome da atualização:").pack(side="left")
        ttk.Entry(controls, textvariable=self.update_name, width=28).pack(side="left", padx=6)
        ttk.Button(controls, text="Analisar", command=self._analyze).pack(side="left", padx=4)
        ttk.Button(controls, text="Alternar aprovação", command=self._toggle_selected_approval).pack(side="left", padx=4)
        ttk.Button(controls, text="Aprovar matches", command=self._approve_matches).pack(side="left", padx=4)
        ttk.Button(controls, text="Executar aprovados", command=self._execute).pack(side="right")

        ttk.Label(self, textvariable=self.summary, anchor="w").pack(
            fill="x", padx=12, pady=(0, 4)
        )
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        columns = ("replace", "copy", "new", "match", "folder", "score")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "replace": "Substituir",
            "copy": "Copiar novo",
            "new": "Ficheiro novo",
            "match": "Match sugerido",
            "folder": "Pasta sugerida",
            "score": "Confiança",
        }
        widths = {"replace": 85, "copy": 95, "new": 270, "match": 300, "folder": 300, "score": 90}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], anchor="w")
        self.table.tag_configure("match", background="#d9f2d9")
        self.table.tag_configure("new", background="#dbeafe")
        self.table.tag_configure("approved", background="#b7e4c7")
        self.table.tag_configure("conflict", background="#ffd6d6")
        vertical_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        horizontal_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )
        self.table.pack(side="left", fill="both", expand=True)
        vertical_scroll.pack(side="right", fill="y")
        horizontal_scroll.pack(side="bottom", fill="x")
        self.table.bind("<<TreeviewSelect>>", self._show_details)
        self.table.bind("<ButtonRelease-1>", self._toggle_checkbox)

        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", padx=12, pady=(0, 10))
        legend = ttk.Label(
            bottom_frame,
            text="🟩 parte comum do nome  |  [x] operação aprovada  |  Substituir move o antigo para Obsoletos",
            anchor="w",
        )
        legend.pack(fill="x", pady=(0, 2))
        self.details = tk.Text(bottom_frame, height=4, wrap="word", state="disabled")
        self.details.tag_configure("common", foreground="#16803c")
        self.details.tag_configure("difference", foreground="black")
        self.details.pack(fill="x")
        self._write_details("Selecione uma linha para ver a análise do match.")
    def _path_row(
        self, parent: ttk.LabelFrame, row: int, label: str, variable: tk.StringVar, command
    ) -> None:
        ttk.Label(parent, text=label, width=20).grid(row=row, column=0, padx=6, pady=4, sticky="w")
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, padx=6, pady=4, sticky="ew")
        ttk.Button(parent, text="Escolher...", command=command).grid(row=row, column=2, padx=6, pady=4)
        parent.columnconfigure(1, weight=1)

    def _choose_new_root(self) -> None:
        selected = filedialog.askdirectory(title="Escolher pasta dos ficheiros novos")
        if selected:
            self.new_root.set(selected)

    def _choose_target_root(self) -> None:
        selected = filedialog.askdirectory(title="Escolher pasta a atualizar")
        if selected:
            self.target_root.set(selected)
            if not self.backup_root.get():
                self.backup_root.set(selected)

    def _choose_backup_root(self) -> None:
        selected = filedialog.askdirectory(title="Escolher base da pasta de obsoletos")
        if selected:
            self.backup_root.set(selected)

    def _analyze(self) -> None:
        try:
            new_root = Path(self.new_root.get())
            target_root = Path(self.target_root.get())
            if not new_root.is_dir() or not target_root.is_dir():
                raise ValueError("Escolha duas pastas válidas.")
            if new_root.resolve() == target_root.resolve():
                raise ValueError("As pastas de origem e destino têm de ser diferentes.")
            self.proposals = analyze(new_root, target_root)
        except (OSError, ValueError) as error:
            messagebox.showerror("Não foi possível analisar", str(error))
            return
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.delete(*self.table.get_children())
        approved_count = sum(proposal.approved for proposal in self.proposals)
        match_count = sum(bool(proposal.matches) for proposal in self.proposals)
        new_count = len(self.proposals) - match_count
        self.summary.set(
            f"{len(self.proposals)} ficheiros analisados | "
            f"{match_count} matches | {new_count} sem match | "
            f"{approved_count} aprovados"
        )
        for index, proposal in enumerate(self.proposals):
            match = proposal.matches[0] if proposal.matches else None
            if match:
                match_name = match.path.name
                prefix = match.common_prefix
                match_text = (
                    f"{match.path.parent.relative_to(Path(self.target_root.get()).resolve())}/"
                    f"🟩{match_name[:prefix]}{match_name[prefix:]}"
                )
            else:
                match_text = "Nenhum match"
            folder_text = str(proposal.suggested_directory.relative_to(Path(self.target_root.get()).resolve())) if proposal.suggested_directory else "-"
            score = f"{match.score:.0%}" if match else f"{proposal.path_score:.0%}"
            tag = "approved" if proposal.approved else ("match" if match else "new")
            self.table.insert(
                "", "end", iid=str(index),
                values=(
                    "[x]" if proposal.approved and proposal.action == "replace" else "[ ]",
                    "[x]" if proposal.approved and proposal.action == "copy" else "[ ]",
                    str(proposal.relative_path),
                    match_text,
                    folder_text,
                    score,
                ),
                tags=(tag,),
            )

    def _selected_proposal(self) -> FileProposal | None:
        selected = self.table.selection()
        if not selected:
            return None
        return self.proposals[int(selected[0])]

    def _toggle_selected_approval(self) -> None:
        proposal = self._selected_proposal()
        if proposal:
            proposal.approved = not proposal.approved
            self._refresh_table()

    def _approve_matches(self) -> None:
        for proposal in self.proposals:
            if proposal.matches and proposal.action == "replace":
                proposal.approved = True
        self._refresh_table()

    def _toggle_checkbox(self, event) -> None:
        if self.table.identify_region(event.x, event.y) != "cell":
            return
        column = self.table.identify_column(event.x)
        if column not in ("#1", "#2"):
            return
        proposal = self._selected_proposal()
        if not proposal:
            return
        if column == "#1" and proposal.matches:
            proposal.action = "replace"
            proposal.approved = not (
                proposal.approved and proposal.action == "replace"
            )
        elif column == "#2":
            proposal.action = "copy"
            proposal.approved = not (
                proposal.approved and proposal.action == "copy"
            )
        self._refresh_table()

    def _show_details(self, _event=None) -> None:
        proposal = self._selected_proposal()
        if not proposal:
            return
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        if proposal.matches:
            best_match = proposal.matches[0]
            prefix_length = best_match.common_prefix
            new_name = proposal.new_path.name
            old_name = best_match.path.name
            self.details.insert("end", "Novo: ")
            self.details.insert("end", new_name[:prefix_length], "common")
            self.details.insert("end", new_name[prefix_length:], "difference")
            self.details.insert("end", f"\nAntigo: {old_name[:prefix_length]}", "common")
            self.details.insert("end", f"{old_name[prefix_length:]}", "difference")
            self.details.insert("end", f"\n\nMatches possíveis: {len(proposal.matches)}")
        else:
            self.details.insert(
                "end",
                f"Sem match de nome.\nPasta sugerida: {proposal.suggested_directory or 'nenhuma'}"
            )
        self.details.configure(state="disabled")

    def _write_details(self, value: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", value)
        self.details.configure(state="disabled")

    def _execute(self) -> None:
        approved = [proposal for proposal in self.proposals if proposal.approved]
        if not approved:
            messagebox.showwarning("Nada aprovado", "Aprove pelo menos um ficheiro.")
            return
        target_root = Path(self.target_root.get())
        backup_base = Path(self.backup_root.get() or target_root)
        default_name = suggested_backup_directory(target_root).name
        update_name = self.update_name.get().strip() or default_name
        backup_directory = backup_base / "Obsoletos" / update_name
        if backup_directory.exists():
            message = f"A pasta {backup_directory} já existe. Os obsoletos serão adicionados sem apagar os anteriores. Continuar?"
        else:
            message = f"Criar a pasta de obsoletos {backup_directory} e executar {len(approved)} alterações?"
        if not messagebox.askyesno("Confirmar operação", message):
            return
        try:
            manifest = execute(approved, target_root, backup_directory)
        except (OSError, ValueError) as error:
            messagebox.showerror("Operação interrompida", str(error))
            return
        messagebox.showinfo("Concluído", f"Operação concluída.\nRelatório: {manifest}")


if __name__ == "__main__":
    UpdaterApp().mainloop()
