"""Диалог авторизации Ollama cloud — общий для GUI-приложений.

Показывается, когда проба облачной модели Ollama вернула HTTP 403:
входа на ollama.com нет. Предлагает запустить ``ollama signin`` прямо
из приложения (открывается браузер для входа).
"""

from __future__ import annotations

from collections.abc import Callable
from tkinter import messagebox

from npazs.llm_models import OLLAMA_SIGNIN_DIALOG_TEXT, run_ollama_signin

#: Тип журнала GUI: ``log(msg, level)``.
LogFn = Callable[..., None]


def offer_ollama_signin(log: LogFn, parent=None) -> bool:
    """Спросить пользователя и запустить ``ollama signin``.

    ``log(msg, level)`` — журнал GUI (вызывается в главном потоке Tk),
    ``parent`` — окно-родитель диалога. Возвращает ``True``, если
    авторизация запущена.
    """
    if not messagebox.askyesno(
        'Ollama: нет авторизации', OLLAMA_SIGNIN_DIALOG_TEXT, parent=parent
    ):
        log(
            'Авторизация Ollama отклонена: cloud-модели будут недоступны '
            'до выполнения `ollama signin`.',
            'warning',
        )
        return False
    try:
        run_ollama_signin()
    except OSError as e:
        log(
            f'Не удалось запустить `ollama signin`: {e}. Выполните команду '
            'вручную в терминале, затем обновите список моделей.',
            'error',
        )
        return False
    log(
        'Запущен `ollama signin` — завершите вход в браузере и нажмите '
        '«Обновить модели».',
        'info',
    )
    return True
