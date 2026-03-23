import tkinter as tk
from tkinter import ttk

root = tk.Tk()
root.geometry("600x300")

# resizable container
paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
paned.pack(fill="both", expand=True)

# left frame (your current frame)
left_frame = ttk.Frame(paned, width=200)
paned.add(left_frame)

# right frame (rest of app)
right_frame = ttk.Frame(paned)
paned.add(right_frame)

# your listbox inside the left frame
listbox = tk.Listbox(left_frame)
listbox.pack(fill="both", expand=True)

root.mainloop()