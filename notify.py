"""Windows notifications from Shortkaar (self-host, the owner's laptop).

The server runs all day on the laptop (autostart.bat), so it is the one
thing that can tap the owner on the shoulder: a reminder that a Google
connection is about to stop, a channel waiting to be connected, the day's
numbers. A toast through Windows PowerShell 5.1's WinRT classes needs no
package; clicking it opens the dashboard. Elsewhere (or when the toast
fails) it does nothing: a reminder is never worth breaking a loop for.
"""
import os
import subprocess
import sys
from xml.sax.saxutils import escape

DASHBOARD = os.environ.get("YT_DASHBOARD_URL") or "http://localhost:5173"
# PowerShell's own AppUserModelID: Windows shows toasts only for a registered
# app, and this one is on every Windows 10/11.
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml([Console]::In.ReadToEnd())
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s').Show($toast)
""" % APP_ID


def toast(title, text, tab="today"):
    """Show one notification; True when Windows took it."""
    if sys.platform != "win32" or os.environ.get("SHORTKAAR_NOTIFY", "1") == "0":
        return False
    link = escape(f"{DASHBOARD}/#app?tab={tab}", {"'": "&apos;"})
    xml = (f"<toast activationType='protocol' launch='{link}' scenario='reminder'>"
           f"<visual><binding template='ToastGeneric'><text>{escape(title[:120])}</text>"
           f"<text>{escape(text[:400])}</text></binding></visual>"
           f"<actions><action content='Open Shortkaar' activationType='protocol' arguments='{link}'/>"
           f"<action content='Later' activationType='system' arguments='dismiss'/></actions></toast>")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                           input=xml, capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
