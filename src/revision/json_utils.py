"""JSON-утилиты: загрузка, сохранение."""

import os
import sys
import re
import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import requests
import threading
import copy
from datetime import datetime, timedelta, date
import traceback
from collections import defaultdict
from bs4 import BeautifulSoup
import json5
import queue
import difflib
from json_repair import repair_json

from npazs.constants import (
    DEFAULT_OLLAMA_MODEL,
    _ollama_base_url,
    _user_retry_callback,
)

from npazs.revision.text_utils import strip_thinking_tags
from npazs.revision.html_utils import normalize_ai_html_response

def load_json(file_path, default):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_html_from_json_response(text, log_callback=None):
    if not text:
        return text
    return normalize_ai_html_response(text, log_callback)
