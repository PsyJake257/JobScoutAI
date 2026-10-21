"""Bounded scroll work; CustomTkinter keeps its normal layout and styling."""

import sys
import tkinter

import customtkinter as ctk


class IdleScrollbar(ctk.CTkScrollbar):
    def set(self, start_value, end_value):
        values = float(start_value), float(end_value)
        if values == (self._start_value, self._end_value):
            return
        self._start_value, self._end_value = values
        start, end = self._get_scrollbar_values_for_minimum_pixel_size()
        # Same rendering primitive as CTkScrollbar (MIT), without its nested
        # update_idletasks(), which repaints the entire UI during scroll/layout.
        recolor = self._draw_engine.draw_rounded_scrollbar(
            self._apply_widget_scaling(self._current_width),
            self._apply_widget_scaling(self._current_height),
            self._apply_widget_scaling(self._corner_radius),
            self._apply_widget_scaling(self._border_spacing), start, end, self._orientation,
        )
        if recolor:
            color = self._button_hover_color if self._hover_state else self._button_color
            color = self._apply_appearance_mode(color)
            self._canvas.itemconfig("scrollbar_parts", fill=color, outline=color)


class ResponsiveScrollableFrame(ctk.CTkScrollableFrame):
    def __init__(self, *args, **kwargs):
        self._global_bindings = []
        self._wheel_pending = None
        self._region_pending = None
        self._drag_pending = None
        self._wheel_amount = {"x": 0.0, "y": 0.0}
        self._content_size = None
        super().__init__(*args, **kwargs)
        old = self._scrollbar
        self._scrollbar = IdleScrollbar(
            self._parent_frame, orientation=self._orientation,
            command=self._scrollbar_command,
            fg_color=old.cget("fg_color"), button_color=old.cget("button_color"),
            button_hover_color=old.cget("button_hover_color"),
        )
        old.destroy()
        command = "yscrollcommand" if self._orientation == "vertical" else "xscrollcommand"
        self._parent_canvas.configure(**{command: self._scrollbar.set})
        self._create_grid()
        self.bind("<Configure>", self._content_configured)

    def bind_all(self, sequence=None, func=None, add=None):
        binding = super().bind_all(sequence, func, add)
        if binding and func is not None:
            self._global_bindings.append((sequence, binding))
        return binding

    def _content_configured(self, event):
        size = event.width, event.height
        if size == self._content_size:
            return
        self._content_size = size
        if self._region_pending is None:
            self._region_pending = self.after_idle(self._update_region)

    def _update_region(self):
        self._region_pending = None
        self._parent_canvas.configure(scrollregion=self._parent_canvas.bbox("all"))

    def _mouse_wheel_all(self, event):
        if not self._check_if_valid_scroll(event.widget):
            return
        axis = "x" if event.state & 1 else "y"
        view = self._parent_canvas.xview if axis == "x" else self._parent_canvas.yview
        if view() == (0.0, 1.0):
            return
        if sys.platform.startswith("win"):
            amount = -event.delta / 120 * self._apply_widget_scaling(48)
        elif sys.platform == "darwin":
            amount = -event.delta
        else:
            amount = -1 if event.num == 4 else 1
        self._wheel_amount[axis] += amount
        if self._wheel_pending is None:
            self._wheel_pending = self.after(16, self._flush_wheel)

    def _flush_wheel(self):
        self._wheel_pending = None
        for axis in ("x", "y"):
            units = int(self._wheel_amount[axis])
            self._wheel_amount[axis] -= units
            if units:
                scroll = self._parent_canvas.xview_scroll if axis == "x" else self._parent_canvas.yview_scroll
                scroll(units, "units")

    def _scrollbar_command(self, *args):
        if args[0] != "moveto":
            self._apply_scroll(*args)
            return
        self._drag_args = args
        if self._drag_pending is None:
            self._drag_pending = self.after(16, self._flush_drag)

    def _flush_drag(self):
        self._drag_pending = None
        self._apply_scroll(*self._drag_args)

    def _apply_scroll(self, *args):
        view = self._parent_canvas.yview if self._orientation == "vertical" else self._parent_canvas.xview
        view(*args)

    def cancel_pending_scroll(self):
        for attribute in ("_wheel_pending", "_drag_pending"):
            pending = getattr(self, attribute, None)
            if pending is not None:
                self.after_cancel(pending)
                setattr(self, attribute, None)
        self._wheel_amount = {"x": 0.0, "y": 0.0}

    def destroy(self):
        for attribute in ("_wheel_pending", "_region_pending", "_drag_pending"):
            pending = getattr(self, attribute, None)
            if pending is not None:
                self.after_cancel(pending)
        root = self._root()
        for sequence, binding in self._global_bindings:
            # Remove only our handlers, never other frames' or textboxes' bindings.
            try:
                root._unbind(("bind", "all", sequence), binding)
            except tkinter.TclError:
                pass
        self._global_bindings.clear()
        super().destroy()
