using System.Drawing;
using System.Windows.Forms;

namespace ChatbotLauncher;

public sealed class TrayController : IDisposable
{
    private readonly LauncherProcessManager _manager;
    private readonly NotifyIcon _notifyIcon;

    public TrayController(LauncherProcessManager manager)
    {
        _manager = manager;
        _notifyIcon = new NotifyIcon
        {
            Text = "Chatbot Launcher",
            Icon = SystemIcons.Application,
            Visible = true,
        };
        _notifyIcon.DoubleClick += (_, _) => _manager.OpenBrowser();
        _notifyIcon.ContextMenuStrip = BuildMenu();
    }

    public event EventHandler? ExitRequested;

    public void Dispose()
    {
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
    }

    private ContextMenuStrip BuildMenu()
    {
        var menu = new ContextMenuStrip();
        menu.Items.Add(BuildActionItem(IsChinese ? "打开" : "Open", () =>
        {
            _manager.OpenBrowser();
            return Task.CompletedTask;
        }));
        menu.Items.Add(BuildActionItem(IsChinese ? "状态" : "Status", async () =>
        {
            var status = await _manager.GetStatusSummaryAsync().ConfigureAwait(true);
            MessageBox.Show(status, LauncherText.ErrorTitle(), MessageBoxButtons.OK, MessageBoxIcon.Information);
        }));
        menu.Items.Add(BuildActionItem(IsChinese ? "重启" : "Restart", () => _manager.RestartAsync()));
        menu.Items.Add(BuildActionItem(IsChinese ? "导出诊断" : "Export diagnostics", async () =>
        {
            var diagnosticsPath = await _manager.ExportDiagnosticsAsync().ConfigureAwait(true);
            MessageBox.Show(
                LauncherText.DiagnosticsExported(diagnosticsPath),
                LauncherText.ErrorTitle(),
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(BuildActionItem(IsChinese ? "退出" : "Exit", () =>
        {
            ExitRequested?.Invoke(this, EventArgs.Empty);
            return Task.CompletedTask;
        }));
        return menu;
    }

    private ToolStripMenuItem BuildActionItem(string text, Func<Task> action)
    {
        var item = new ToolStripMenuItem(text);
        item.Click += async (_, _) =>
        {
            try
            {
                await action().ConfigureAwait(true);
            }
            catch (LauncherUserFacingException ex)
            {
                MessageBox.Show(ex.Message, LauncherText.ErrorTitle(), MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, LauncherText.ErrorTitle(), MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        };
        return item;
    }

    private static bool IsChinese =>
        string.Equals(
            System.Globalization.CultureInfo.CurrentUICulture.TwoLetterISOLanguageName,
            "zh",
            StringComparison.OrdinalIgnoreCase);
}

public sealed class LauncherApplicationContext : ApplicationContext
{
    private readonly LauncherProcessManager _manager;
    private readonly TrayController _trayController;

    public LauncherApplicationContext(LauncherProcessManager manager, TrayController trayController)
    {
        _manager = manager;
        _trayController = trayController;
        _trayController.ExitRequested += OnExitRequested;
    }

    protected override void ExitThreadCore()
    {
        _manager.StopAsync().GetAwaiter().GetResult();
        _trayController.Dispose();
        base.ExitThreadCore();
    }

    private void OnExitRequested(object? sender, EventArgs e)
    {
        ExitThread();
    }
}
