import os, math
from datetime import datetime, date
import tkinter as tk
from tkinter import filedialog, messagebox

# ---- парсер даты (вместо @staticmethod) ----
def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except:
            pass
    raise ValueError("Некорректная дата: " + s)

class Contract:
    def __init__(self, cid, customer, day, amount):
        self.cid = cid.strip()
        self.customer = customer.strip()
        self.day = day
        self.amount = amount
        self.validate()

    def validate(self):
        if not self.cid or not self.customer:
            raise ValueError("Пустой id или заказчик")
        if self.amount is not None and self.amount < 0:
            raise ValueError("Сумма < 0")

    @classmethod
    def from_row(cls, r):
        cid = (r.get("id") or r.get("contract_id") or r.get("cid") or "").strip()
        cust = (r.get("customer") or r.get("client") or r.get("name") or "").strip()
        d_raw = (r.get("date") or r.get("day") or r.get("created_at") or "").strip()
        d = parse_date(d_raw)
        a_raw = (r.get("amount") or r.get("sum") or r.get("price") or "").replace(",", ".").strip()
        a = None if a_raw == "" else float(a_raw)
        return cls(cid, cust, d, a)

    def to_row(self):
        return {
            "id": self.cid,
            "customer": self.customer,
            "date": self.day.strftime("%Y-%m-%d"),
            "amount": "" if self.amount is None else f"{self.amount:.2f}"
        }

def detect_delim(line):
    cands = [",", ";", "\t", "|"]
    best, best_parts = ",", 1
    for d in cands:
        parts = line.rstrip("\n\r").split(d)
        if len(parts) > best_parts:
            best, best_parts = d, len(parts)
    return best

def read_table_text(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.readlines() if ln.strip() != ""]
    if not lines:
        return [], []
    delim = detect_delim(lines[0])
    header = [h.strip() for h in lines[0].rstrip("\n\r").split(delim)]
    rows = []
    for ln in lines[1:]:
        parts = [p.strip() for p in ln.rstrip("\n\r").split(delim)]
        if len(parts) < len(header):
            parts += [""] * (len(header) - len(parts))
        elif len(parts) > len(header):
            parts = parts[:len(header)]
        rows.append(parts)
    return header, rows

def rows_to_contracts(headers, rows):
    hdr_lower = [h.strip().lower() for h in headers]
    items, bad = [], 0
    for parts in rows:
        rd = {h: (parts[i] if i < len(parts) else "") for i, h in enumerate(hdr_lower)}
        try:
            items.append(Contract.from_row(rd))
        except Exception:
            bad += 1
    return items, bad

def save_table_text(path, headers, rows):
    delim = ","
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(delim.join(headers) + "\n")
        for r in rows:
            out = []
            for cell in r:
                cell = "" if cell is None else str(cell)
                if any(ch in cell for ch in [",", ";", "\t", "|", "\"", "\n"]):
                    cell = "\"" + cell.replace("\"", "\"\"") + "\""
                out.append(cell)
            f.write(delim.join(out) + "\n")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Новиков ЛР №8")  # <-- новое название окна
        self.geometry("1100x800")
        self.items = []
        self._last_pie = None

        top = tk.Frame(self); top.pack(fill="x", pady=4)
        tk.Button(top, text="Загрузить TXT/CSV", command=self.load_table).pack(side="left", padx=4)
        tk.Button(top, text="Сохранить как TXT/CSV", command=self.save_table).pack(side="left", padx=4)
        tk.Button(top, text="Сегм. по заказчикам", command=self.seg_customers).pack(side="left", padx=4)
        tk.Button(top, text="Сегм. по месяцам (тек. год)", command=self.seg_months).pack(side="left", padx=4)

        self.split = tk.PanedWindow(self, orient="vertical", sashwidth=6); self.split.pack(fill="both", expand=1)

        plot_frame = tk.Frame(self.split); plot_frame.pack(fill="both", expand=1)
        self.canvas = tk.Canvas(plot_frame, bg="white", width=980, height=560,
                                highlightthickness=1, highlightbackground="#ddd")
        self.canvas.pack(fill="both", expand=1, padx=8, pady=8)
        self.canvas.bind("<Configure>", self._on_resize_canvas)
        self.split.add(plot_frame, minsize=420)

        list_frame = tk.Frame(self.split, height=180); list_frame.pack_propagate(False)
        sb = tk.Scrollbar(list_frame, orient="vertical")
        self.listbox = tk.Listbox(list_frame, yscrollcommand=sb.set)
        sb.config(command=self.listbox.yview)
        self.listbox.pack(side="left", fill="both", expand=1, padx=(8,0), pady=8)
        sb.pack(side="left", fill="y", padx=(0,8), pady=8)
        self.split.add(list_frame, minsize=120)

        self.status = tk.StringVar(value="Готово")
        tk.Label(self, textvariable=self.status, anchor="w").pack(fill="x")

    def _on_resize_canvas(self, event):
        if self._last_pie:
            data, title = self._last_pie
            self.draw_pie(data, title)

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for c in self.items:
            amt = "" if c.amount is None else f"{c.amount:.0f}"
            self.listbox.insert(tk.END, f"{c.cid} | {c.customer} | {c.day.strftime('%Y-%m-%d')} | {amt}")
        self.status.set(f"Договоров: {len(self.items)}")

    def draw_pie(self, data_dict, title="Диаграмма"):
        self._last_pie = (data_dict, title)
        cv = self.canvas; cv.delete("all")
        w = cv.winfo_width() or cv.winfo_reqwidth()
        h = cv.winfo_height() or cv.winfo_reqheight()

        r = int(min(w, h) * 0.38)
        cx = int(w * 0.40)
        cy = int(h * 0.52)

        cv.create_text(w // 2, 22, text=title, font=("Segoe UI", 12, "bold"))

        vals = [v for v in data_dict.values() if v > 0]
        if not vals:
            cv.create_text(w // 2, h // 2, text="Нет данных"); return

        items = sorted(data_dict.items(), key=lambda kv: kv[1], reverse=True)  # без «Прочие»
        total = sum(v for _, v in items)
        bbox = (cx - r, cy - r, cx + r, cy + r)
        pal = ["#f66", "#6f6", "#66f", "#fc3", "#3cf", "#c6f", "#aaa", "#6cc", "#c96", "#9c6", "#ddd"]

        a = 0.0
        leg_x = cx + r + 28
        leg_y = int(h * 0.16)
        leg_line_h = 18
        leg_col_w = 240

        for i, (label, value) in enumerate(items):
            ext = 360.0 * value / total
            col = pal[i % len(pal)]
            cv.create_arc(bbox, start=a, extent=ext, fill=col, outline="white")

            mid = math.radians(a + ext / 2)
            px = cx + 0.7 * r * math.cos(mid)
            py = cy - 0.7 * r * math.sin(mid)
            cv.create_text(px, py, text=f"{value * 100 / total:.0f}%")

            if leg_y > h - 30:
                leg_y = int(h * 0.16)
                leg_x += leg_col_w

            cv.create_rectangle(leg_x, leg_y - 10, leg_x + 10, leg_y, fill=col, outline=col)
            cv.create_text(leg_x + 16, leg_y - 5, anchor="w", text=f"{label}: {value}")
            leg_y += leg_line_h

            a += ext

        cv.create_oval(bbox, outline="#444")

    def load_table(self):
        p = filedialog.askopenfilename(
            title="Выберите TXT/CSV",
            filetypes=[("TXT/CSV", "*.txt *.csv"), ("Все файлы", "*.*")]
        )
        if not p: return
        try:
            headers, rows = read_table_text(p)
            if not headers:
                messagebox.showinfo("Загрузка", "Файл пуст"); return
            new_items, bad = rows_to_contracts(headers, rows)
            self.items = new_items
            self.refresh_list()
            messagebox.showinfo("Загрузка",
                                f"{os.path.basename(p)}\nЗагружено: {len(self.items)}, пропущено: {bad}")
        except Exception as e:
            messagebox.showerror("Ошибка чтения", str(e))

    def save_table(self):
        if not self.items:
            messagebox.showinfo("Сохранение", "Список пуст"); return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("TXT", "*.txt"), ("CSV", "*.csv"), ("Все файлы", "*.*")],
            title="Сохранить как TXT/CSV",
            initialfile="Новиков ЛР №8.txt"
        )
        if not p: return
        try:
            headers = ["id", "customer", "date", "amount"]
            rows = []
            for c in self.items:
                r = c.to_row()
                rows.append([r["id"], r["customer"], r["date"], r["amount"]])
            save_table_text(p, headers, rows)
            self.status.set("Сохранено: " + os.path.basename(p))
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", str(e))

    def seg_customers(self):
        d = {}
        for c in self.items:
            d[c.customer] = d.get(c.customer, 0) + 1
        self.draw_pie(d, "По заказчикам (кол-во)")

    def seg_months(self):
        year_data = {}
        for c in self.items:
            y = c.day.year
            if y not in year_data:
                year_data[y] = {f"{i:02d}": 0 for i in range(1, 13)}
            key = f"{c.day.month:02d}"
            year_data[y][key] += 1

        if not year_data:
            messagebox.showinfo("Информация", "Нет данных для построения диаграммы"); return

        current_year = date.today().year
        selected_year = current_year if current_year in year_data else min(year_data.keys())

        d = year_data[selected_year]
        mnames = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
        pretty = {mnames[int(k)-1]: v for k, v in d.items()}
        self.draw_pie(pretty, f"По месяцам ({selected_year})")

if __name__ == "__main__":
    App().mainloop()
