from __future__ import annotations

import tkinter as tk
import sys
import traceback
import tempfile
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
        self.selected_index: int | None = None
        self._build_ui()

    def write_error_log(self, error: BaseException) -> Path:
        log_directory = Path(tempfile.gettempdir())
        log_path = log_directory / "Atualizador.log"
        log_path.write_text(
            "".join(traceback.format_exception(error)),
            encoding="utf-8",
        )
        return log_path

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
        self.table_canvas = tk.Canvas(table_frame, highlightthickness=0)
        vertical_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table_canvas.yview)
        horizontal_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table_canvas.xview)
        self.table_canvas.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )
        self.table_content = ttk.Frame(self.table_canvas)
        self.table_canvas.create_window((0, 0), window=self.table_content, anchor="nw")
        self.table_content.bind(
            "<Configure>",
            lambda _event: self.table_canvas.configure(
                scrollregion=self.table_canvas.bbox("all")
            ),
        )
        self.table_canvas.pack(side="left", fill="both", expand=True)
        vertical_scroll.pack(side="right", fill="y")
        horizontal_scroll.pack(side="bottom", fill="x")
        self._build_table_header()

        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", padx=12, pady=(0, 10))
        legend = ttk.Label(
            bottom_frame,
            text="🟩 parte comum do nome  |  [x] operação aprovada  |  Substituir move o antigo para Obsoletos",
            anchor="w",
        )
        legend.pack(fill="x", pady=(0, 2))
        self.details = tk.Text(
            bottom_frame,
            height=4,
            wrap="none",
            state="disabled",
            font=("Courier New", 11),
        )
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
        self.summary.set("A analisar ficheiros...")
        self.update_idletasks()
        self.after(50, self._run_analysis)

    def _run_analysis(self) -> None:
        try:
            new_root = Path(self.new_root.get())
            target_root = Path(self.target_root.get())
            if not new_root.is_dir() or not target_root.is_dir():
                raise ValueError("Escolha duas pastas válidas.")
            if new_root.resolve() == target_root.resolve():
                raise ValueError("As pastas de origem e destino têm de ser diferentes.")
            self.proposals = analyze(new_root, target_root)
        except Exception as error:
            log_path = self.write_error_log(error)
            messagebox.showerror(
                "Não foi possível analisar",
                f"{error}\n\nDetalhes: {log_path}",
            )
            return
        try:
            self._refresh_table()
        except Exception as error:
            log_path = self.write_error_log(error)
            messagebox.showerror(
                "Não foi possível mostrar a análise",
                f"{error}\n\nDetalhes: {log_path}",
            )

    def _refresh_table(self) -> None:
        for child in self.table_content.winfo_children():
            if getattr(child, "_is_table_rows", False):
                child.destroy()
        self._update_summary()
        rows = ttk.Frame(self.table_content)
        rows._is_table_rows = True
        rows.pack(fill="x")
        self._render_rows_batch(rows, 0, 20)

    def _render_rows_batch(self, rows, start: int, batch_size: int) -> None:
        end = min(start + batch_size, len(self.proposals))
        for index in range(start, end):
            proposal = self.proposals[index]
            match = proposal.matches[0] if proposal.matches else None
            self._build_table_row(rows, index, proposal, match)
        if end < len(self.proposals):
            self.summary.set(
                f"A mostrar {end}/{len(self.proposals)} ficheiros..."
            )
            self.after(10, lambda: self._render_rows_batch(rows, end, batch_size))
        else:
            self._update_summary()

    def _update_summary(self) -> None:
        approved_count = sum(proposal.approved for proposal in self.proposals)
        match_count = sum(bool(proposal.matches) for proposal in self.proposals)
        unchanged_count = sum(proposal.unchanged for proposal in self.proposals)
        new_count = len(self.proposals) - match_count
        self.summary.set(
            f"{len(self.proposals)} ficheiros analisados | "
            f"{match_count - unchanged_count} matches | "
            f"{unchanged_count} sem alteração | {new_count} sem match | "
            f"{approved_count} aprovados"
        )

    def _build_table_header(self) -> None:
        header = ttk.Frame(self.table_content)
        widths = (8, 10, 26, 34, 34, 26, 10)
        labels = (
            "Substituir",
            "Copiar novo",
            "Pasta de origem",
            "Ficheiro novo",
            "Match sugerido",
            "Pasta sugerida",
            "Confiança",
        )
        for column, (label, width) in enumerate(zip(labels, widths)):
            ttk.Label(header, text=label, anchor="center", relief="raised").grid(
                row=0, column=column, sticky="nsew"
            )
            header.columnconfigure(column, minsize=width * 10, weight=1)
        header.pack(fill="x")

    def _build_table_row(self, parent, index: int, proposal: FileProposal, match) -> None:
        row = tk.Frame(parent, background="#eeeeee" if proposal.unchanged else "white")
        row.pack(fill="x")
        columns = (8, 10, 26, 34, 34, 26, 10)
        for column, width in enumerate(columns):
            row.grid_columnconfigure(column, minsize=width * 10, weight=1)
        replace_var = tk.BooleanVar(value=proposal.approved and proposal.action == "replace")
        copy_var = tk.BooleanVar(value=proposal.approved and proposal.action == "copy")
        tk.Checkbutton(
            row,
            variable=replace_var,
            command=lambda: self._set_row_action(index, "replace", replace_var, copy_var),
            state="disabled" if proposal.unchanged or not proposal.matches else "normal",
            background=row["background"],
        ).grid(row=0, column=0)
        tk.Checkbutton(
            row,
            variable=copy_var,
            command=lambda: self._set_row_action(index, "copy", replace_var, copy_var),
            state="disabled" if proposal.unchanged else "normal",
            background=row["background"],
        ).grid(row=0, column=1)
        match_prefix = match.common_prefix if match else 0
        source_folder = str(proposal.relative_path.parent)
        if source_folder == ".":
            source_folder = "."
        ttk.Label(row, text=source_folder or ".", anchor="w").grid(row=0, column=2, sticky="ew")
        self._colored_name_cell(row, 3, proposal.relative_path.name, match_prefix if match else 0)
        self._colored_path_cell(
            row,
            4,
            match.path if match else None,
            match_prefix if match else 0,
        )
        folder = (
            str(proposal.suggested_directory.relative_to(Path(self.target_root.get()).resolve()))
            if proposal.suggested_directory else "-"
        )
        ttk.Label(row, text=folder, anchor="w").grid(row=0, column=5, sticky="ew")
        score = "Sem alteração" if proposal.unchanged else (
            f"{match.score:.0%}" if match else f"{proposal.path_score:.0%}"
        )
        ttk.Label(row, text=score, anchor="w").grid(row=0, column=6, sticky="ew")
        for widget in row.winfo_children():
            widget.bind("<Button-1>", lambda _event, i=index: self._select_row(i))

    def _colored_path_cell(self, parent, column: int, path: Path | None, common_prefix: int) -> None:
        text = tk.Text(parent, height=1, width=1, wrap="none", borderwidth=0, highlightthickness=0)
        text.tag_configure("common", foreground="#16803c")
        text.tag_configure("difference", foreground="black")
        if path is None:
            text.insert("1.0", "Nenhum match")
        else:
            self._insert_colored_name(text, path.name, common_prefix)
        text.configure(state="disabled")
        text.grid(row=0, column=column, sticky="ew")

    def _colored_name_cell(self, parent, column: int, name: str, common_prefix: int) -> None:
        text = tk.Text(parent, height=1, width=1, wrap="none", borderwidth=0, highlightthickness=0)
        text.tag_configure("common", foreground="#16803c")
        text.tag_configure("difference", foreground="black")
        self._insert_colored_name(text, name, common_prefix)
        text.configure(state="disabled")
        text.grid(row=0, column=column, sticky="ew")

    def _insert_colored_name(self, text: tk.Text, name: str, common_prefix: int) -> None:
        stem_length = common_prefix
        text.insert("1.0", name[:stem_length], "common")
        text.insert("end", name[stem_length:], "difference")

    def _select_row(self, index: int) -> None:
        self.selected_index = index
        self._show_details()

    def _selected_proposal(self) -> FileProposal | None:
        if self.selected_index is None:
            return None
        return self.proposals[self.selected_index]

    def _set_row_action(self, index, action, replace_var, copy_var) -> None:
        proposal = self.proposals[index]
        selected = replace_var if action == "replace" else copy_var
        other = copy_var if action == "replace" else replace_var
        if selected.get():
            other.set(False)
            proposal.action = action
            proposal.approved = True
        else:
            proposal.approved = False
        self.selected_index = index
        self._update_summary()

    def _toggle_selected_approval(self) -> None:
        proposal = self._selected_proposal()
        if proposal:
            proposal.approved = not proposal.approved
            self._update_summary()

    def _approve_matches(self) -> None:
        for proposal in self.proposals:
            if proposal.matches and not proposal.unchanged and proposal.action == "replace":
                proposal.approved = True
        self._refresh_table()

    def _show_details(self, _event=None) -> None:
        proposal = self._selected_proposal()
        if not proposal:
            return
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        if proposal.matches:
            if proposal.unchanged:
                self._write_details("Mesmo nome encontrado no destino. Sem alteração de versão.")
                return
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
