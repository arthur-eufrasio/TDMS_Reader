import tkinter as tk

from gui.controllers.main_controller import MainController
from gui.views.main_window import MainWindow


def main() -> None:
    root = tk.Tk()
    view = MainWindow(root)
    MainController(view)
    root.mainloop()


if __name__ == "__main__":
    main()
