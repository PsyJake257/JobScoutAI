"""Presentation adapters for readable text without changing stored values."""

from customtkinter import *
import customtkinter as _ctk

from ui_text import anzeigetext
from scroll_widgets import ResponsiveScrollableFrame as CTkScrollableFrame


class _Text:
    def __init__(self, *args, **kwargs):
        for name in ("text", "placeholder_text"):
            if name in kwargs:
                kwargs[name] = anzeigetext(kwargs[name])
        super().__init__(*args, **kwargs)

    def configure(self, **kwargs):
        for name in ("text", "placeholder_text"):
            if name in kwargs:
                kwargs[name] = anzeigetext(kwargs[name])
        return super().configure(**kwargs)


class CTkLabel(_Text, _ctk.CTkLabel):
    pass


class CTkEntry(_Text, _ctk.CTkEntry):
    pass


class CTkCheckBox(_Text, _ctk.CTkCheckBox):
    pass


class CTkSwitch(_Text, _ctk.CTkSwitch):
    pass


def _farben(wert):
    return list(wert) if isinstance(wert, (tuple, list)) else [wert, wert]


def kontrastfarbe(hintergrund):
    rgb = [int(hintergrund[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [wert / 12.92 if wert <= 0.04045 else ((wert + 0.055) / 1.055) ** 2.4 for wert in rgb]
    helligkeit = sum(wert * gewicht for wert, gewicht in zip(linear, (0.2126, 0.7152, 0.0722)))
    return "#071522" if helligkeit > 0.179 else "#FFFFFF"


class CTkButton(_Text, _ctk.CTkButton):
    def __init__(self, *args, **kwargs):
        self._aktionsfarbe = kwargs.get("fg_color", _ctk.ThemeManager.theme["CTkButton"]["fg_color"])
        super().__init__(*args, **kwargs)
        self.configure()

    def configure(self, **kwargs):
        if "fg_color" in kwargs:
            self._aktionsfarbe = kwargs["fg_color"]
        state = kwargs.get("state", getattr(self, "_state", "normal"))
        if state == "disabled":
            kwargs.update(fg_color=("#DBE3EB", "#354553"), text_color_disabled=("#465462", "#E0E8F0"))
        else:
            kwargs["fg_color"] = self._aktionsfarbe
            farben = _farben(self._aktionsfarbe)
            if all(isinstance(farbe, str) and farbe.startswith("#") and len(farbe) == 7 for farbe in farben):
                kwargs["text_color"] = tuple(kontrastfarbe(farbe) for farbe in farben)
        return super().configure(**kwargs)


class CTkComboBox(_ctk.CTkComboBox):
    def __init__(self, *args, **kwargs):
        self._originalwerte = list(kwargs.get("values", []))
        self._datenvariable = kwargs.pop("variable", None)
        self._anzeigevariable = _ctk.StringVar(value=anzeigetext(self._datenvariable.get()) if self._datenvariable is not None else "")
        self._synchronisiert = False
        self._daten_trace = None
        kwargs["values"] = [anzeigetext(wert) for wert in self._originalwerte]
        kwargs["variable"] = self._anzeigevariable
        if kwargs.get("command"):
            command = kwargs["command"]
            kwargs["command"] = lambda wert: command(self._originalwert(wert))
        super().__init__(*args, **kwargs)
        self._anzeige_trace = self._anzeigevariable.trace_add("write", self._anzeige_geaendert)
        if self._datenvariable is not None:
            self._daten_trace = self._datenvariable.trace_add("write", self._daten_geaendert)

    def _originalwert(self, wert):
        return next((original for original in self._originalwerte if anzeigetext(original) == wert), wert)

    def _daten_geaendert(self, *_):
        if not self._synchronisiert:
            self._synchronisiert = True
            try:
                self._anzeigevariable.set(anzeigetext(self._datenvariable.get()))
            finally:
                self._synchronisiert = False

    def _anzeige_geaendert(self, *_):
        if self._datenvariable is not None and not self._synchronisiert:
            self._synchronisiert = True
            try:
                self._datenvariable.set(self.get())
            finally:
                self._synchronisiert = False

    def get(self):
        return self._originalwert(super().get())

    def set(self, wert):
        return super().set(anzeigetext(wert))

    def configure(self, **kwargs):
        if "values" in kwargs:
            self._originalwerte = list(kwargs["values"])
            kwargs["values"] = [anzeigetext(wert) for wert in self._originalwerte]
        if kwargs.get("command"):
            command = kwargs["command"]
            kwargs["command"] = lambda wert: command(self._originalwert(wert))
        return super().configure(**kwargs)

    def cget(self, name):
        return self._originalwerte if name == "values" else super().cget(name)

    def destroy(self):
        if self._daten_trace is not None:
            self._datenvariable.trace_remove("write", self._daten_trace)
        self._anzeigevariable.trace_remove("write", self._anzeige_trace)
        super().destroy()


class CTkSegmentedButton(_ctk.CTkSegmentedButton):
    def _create_button(self, index, value):
        button = super()._create_button(index, value)
        button.configure(text=anzeigetext(value))
        return button


class CTkToplevel(_ctk.CTkToplevel):
    def title(self, text=None):
        return super().title(anzeigetext(text)) if text is not None else super().title()
