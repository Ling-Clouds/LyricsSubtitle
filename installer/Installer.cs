using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

namespace LyricsSubtitleSetup
{
    internal static class Program
    {
        internal const string AppName = "歌词打轴";
        internal const string AppVersion = "0.1.0";
        internal const string AppId = "LyricsSubtitle";
        internal const string Publisher = "Ling-Clouds";
        internal const string RepoUrl = "https://github.com/Ling-Clouds/LyricsSubtitle";
        internal const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\LyricsSubtitle";

        internal static string DefaultDir
        {
            get
            {
                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    @"Programs\LyricsSubtitle");
            }
        }

        [STAThread]
        private static int Main(string[] args)
        {
            bool silent = HasArg(args, "--silent");
            if (silent)
            {
                string dir = ArgValue(args, "--dir");
                if (String.IsNullOrEmpty(dir))
                {
                    dir = DefaultDir;
                }
                try
                {
                    Install(dir, !HasArg(args, "--no-shortcuts"), !HasArg(args, "--no-registry"), null);
                    return 0;
                }
                catch
                {
                    return 3;
                }
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
            return 0;
        }

        internal static List<string> Install(string path, bool shortcuts, bool registry, Action<int> progress)
        {
            string target = NormalizeTarget(path);
            Directory.CreateDirectory(target);

            Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip");
            if (payload == null)
            {
                throw new InvalidOperationException("安装包中缺少 payload.zip");
            }

            using (payload)
            {
                using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
                {
                    int total = archive.Entries.Count;
                    int index = 0;
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        if (String.IsNullOrEmpty(entry.FullName))
                        {
                            continue;
                        }
                        string relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                        string destination = Path.GetFullPath(Path.Combine(target, relative));
                        if (!IsInside(target, destination))
                        {
                            continue;
                        }
                        if (entry.FullName.EndsWith("/"))
                        {
                            Directory.CreateDirectory(destination);
                        }
                        else
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(destination));
                            using (Stream input = entry.Open())
                            using (FileStream output = File.Create(destination))
                            {
                                input.CopyTo(output);
                            }
                        }
                        index++;
                        if (progress != null && (index % 8 == 0 || index == total))
                        {
                            progress((int)(index * 100L / Math.Max(1, total)));
                        }
                    }
                }
            }

            if (!File.Exists(Path.Combine(target, "LyricsSubtitle.exe")))
            {
                throw new InvalidOperationException("安装包校验失败：没有找到 LyricsSubtitle.exe");
            }

            List<string> warnings = new List<string>();
            if (shortcuts)
            {
                warnings.AddRange(CreateShortcuts(target));
            }
            if (registry)
            {
                try
                {
                    WriteRegistry(target);
                }
                catch (Exception ex)
                {
                    warnings.Add("卸载信息写入失败：" + ex.Message);
                }
            }
            return warnings;
        }

        internal static string NormalizeTarget(string path)
        {
            string target = Path.GetFullPath(path.Trim());
            target = target.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (String.IsNullOrEmpty(target))
            {
                throw new ArgumentException("安装路径不能为空");
            }
            string root = Path.GetPathRoot(target);
            if (String.Equals(target, root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
            {
                throw new ArgumentException("不能安装到磁盘根目录");
            }
            string windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
            if (target.StartsWith(windows + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            {
                throw new ArgumentException("不能安装到 Windows 目录");
            }
            if (File.Exists(target))
            {
                throw new ArgumentException("目标路径已经存在且不是文件夹");
            }
            return target;
        }

        private static bool IsInside(string root, string path)
        {
            string prefix = root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            return path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
        }

        private static List<string> CreateShortcuts(string target)
        {
            List<string> errors = new List<string>();
            string exe = Path.Combine(target, "LyricsSubtitle.exe");
            string uninstall = Path.Combine(target, "Uninstall.exe");

            string startFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                @"Microsoft\Windows\Start Menu\Programs",
                AppName);
            try
            {
                Directory.CreateDirectory(startFolder);
                CreateShortcut(Path.Combine(startFolder, AppName + ".lnk"), exe, "");
                if (File.Exists(uninstall))
                {
                    CreateShortcut(
                        Path.Combine(startFolder, "卸载 " + AppName + ".lnk"),
                        uninstall,
                        "--dir \"" + target + "\"");
                }
            }
            catch (Exception ex)
            {
                errors.Add("开始菜单快捷方式创建失败：" + ex.Message);
            }

            try
            {
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                CreateShortcut(Path.Combine(desktop, AppName + ".lnk"), exe, "");
            }
            catch (Exception ex)
            {
                errors.Add("桌面快捷方式创建失败：" + ex.Message);
            }
            return errors;
        }

        private static void CreateShortcut(string link, string target, string arguments)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(link));
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null)
            {
                throw new InvalidOperationException("WScript.Shell 不可用");
            }
            object shell = Activator.CreateInstance(shellType);
            object shortcut = null;
            try
            {
                shortcut = shellType.InvokeMember(
                    "CreateShortcut",
                    BindingFlags.InvokeMethod,
                    null,
                    shell,
                    new object[] { link });
                Type shortcutType = shortcut.GetType();
                shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
                shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { Path.GetDirectoryName(target) });
                shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { target + ",0" });
                shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { arguments });
                shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { AppName });
                shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
            }
            finally
            {
                if (shortcut != null)
                {
                    Marshal.ReleaseComObject(shortcut);
                }
                if (shell != null)
                {
                    Marshal.ReleaseComObject(shell);
                }
            }
        }

        private static void WriteRegistry(string target)
        {
            string exe = Path.Combine(target, "LyricsSubtitle.exe");
            string uninstall = Path.Combine(target, "Uninstall.exe");
            long total = 0;
            foreach (string file in Directory.GetFiles(target, "*", SearchOption.AllDirectories))
            {
                try
                {
                    total += new FileInfo(file).Length;
                }
                catch
                {
                }
            }

            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallKey))
            {
                key.SetValue("DisplayName", AppName);
                key.SetValue("DisplayVersion", AppVersion);
                key.SetValue("Publisher", Publisher);
                key.SetValue("InstallLocation", target);
                key.SetValue("DisplayIcon", exe);
                key.SetValue("UninstallString", "\"" + uninstall + "\" --dir \"" + target + "\"");
                key.SetValue("QuietUninstallString", "\"" + uninstall + "\" --silent --dir \"" + target + "\"");
                key.SetValue("URLInfoAbout", RepoUrl);
                key.SetValue("EstimatedSize", (int)(total / 1024L), RegistryValueKind.DWord);
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
        }

        internal static string ReadResource(string name)
        {
            using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
            {
                if (stream == null)
                {
                    return "（缺少资源：" + name + "）";
                }
                using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                {
                    return reader.ReadToEnd();
                }
            }
        }

        internal static bool HasArg(string[] args, string name)
        {
            foreach (string arg in args)
            {
                if (String.Equals(arg, name, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        internal static string ArgValue(string[] args, string name)
        {
            string prefix = name + "=";
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i].StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                {
                    return args[i].Substring(prefix.Length);
                }
                if (String.Equals(args[i], name, StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    return args[i + 1];
                }
            }
            return null;
        }
    }

    internal sealed class InstallerForm : Form
    {
        private readonly TextBox pathBox;
        private readonly TextBox licenseBox;
        private readonly CheckBox acceptBox;
        private readonly CheckBox desktopBox;
        private readonly CheckBox launchBox;
        private readonly ProgressBar progress;
        private readonly Label statusLabel;
        private readonly Button installButton;
        private readonly Button browseButton;
        private readonly BackgroundWorker worker;
        private string installedTarget;

        internal InstallerForm()
        {
            Text = Program.AppName + " 安装程序";
            ClientSize = new Size(820, 660);
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            Font = new Font("Microsoft YaHei UI", 9F);
            try
            {
                Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch
            {
            }

            Label title = new Label();
            title.Text = "安装 " + Program.AppName;
            title.Font = new Font("Microsoft YaHei UI", 18F, FontStyle.Bold);
            title.AutoSize = true;
            title.Location = new Point(18, 16);
            Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "版本 " + Program.AppVersion + " · 按用户安装，不需要管理员权限";
            subtitle.AutoSize = true;
            subtitle.Location = new Point(20, 58);
            Controls.Add(subtitle);

            GroupBox pathGroup = new GroupBox();
            pathGroup.Text = "安装位置";
            pathGroup.Location = new Point(18, 90);
            pathGroup.Size = new Size(784, 62);
            Controls.Add(pathGroup);

            pathBox = new TextBox();
            pathBox.Text = Program.DefaultDir;
            pathBox.Location = new Point(12, 24);
            pathBox.Width = 650;
            pathGroup.Controls.Add(pathBox);

            browseButton = new Button();
            browseButton.Text = "浏览…";
            browseButton.Location = new Point(672, 22);
            browseButton.Size = new Size(96, 26);
            browseButton.Click += BrowseClick;
            pathGroup.Controls.Add(browseButton);

            GroupBox licenseGroup = new GroupBox();
            licenseGroup.Text = "许可证与第三方组件";
            licenseGroup.Location = new Point(18, 162);
            licenseGroup.Size = new Size(784, 330);
            Controls.Add(licenseGroup);

            licenseBox = new TextBox();
            licenseBox.Multiline = true;
            licenseBox.ReadOnly = true;
            licenseBox.ScrollBars = ScrollBars.Vertical;
            licenseBox.WordWrap = true;
            licenseBox.Location = new Point(10, 22);
            licenseBox.Size = new Size(762, 296);
            licenseBox.Font = new Font("Microsoft YaHei UI", 8.5F);
            licenseBox.Text = Program.ReadResource("license.txt") + "\r\n\r\n" + Program.ReadResource("notices.txt");
            licenseBox.SelectionStart = 0;
            licenseGroup.Controls.Add(licenseBox);

            acceptBox = new CheckBox();
            acceptBox.Text = "我已阅读并同意 MIT 许可证及第三方组件声明";
            acceptBox.AutoSize = true;
            acceptBox.Location = new Point(20, 502);
            acceptBox.CheckedChanged += AcceptChanged;
            Controls.Add(acceptBox);

            desktopBox = new CheckBox();
            desktopBox.Text = "创建桌面快捷方式";
            desktopBox.AutoSize = true;
            desktopBox.Checked = true;
            desktopBox.Location = new Point(20, 530);
            Controls.Add(desktopBox);

            launchBox = new CheckBox();
            launchBox.Text = "完成后启动";
            launchBox.AutoSize = true;
            launchBox.Checked = true;
            launchBox.Location = new Point(190, 530);
            Controls.Add(launchBox);

            progress = new ProgressBar();
            progress.Location = new Point(20, 558);
            progress.Size = new Size(780, 18);
            progress.Minimum = 0;
            progress.Maximum = 100;
            Controls.Add(progress);

            statusLabel = new Label();
            statusLabel.Text = "准备安装";
            statusLabel.AutoSize = true;
            statusLabel.Location = new Point(20, 584);
            Controls.Add(statusLabel);

            installButton = new Button();
            installButton.Text = "安装";
            installButton.Location = new Point(682, 612);
            installButton.Size = new Size(118, 32);
            installButton.Enabled = false;
            installButton.Click += InstallClick;
            Controls.Add(installButton);

            Button cancelButton = new Button();
            cancelButton.Text = "取消";
            cancelButton.Location = new Point(570, 612);
            cancelButton.Size = new Size(100, 32);
            cancelButton.Click += delegate { Close(); };
            Controls.Add(cancelButton);

            worker = new BackgroundWorker();
            worker.WorkerReportsProgress = true;
            worker.DoWork += WorkerDoWork;
            worker.ProgressChanged += WorkerProgressChanged;
            worker.RunWorkerCompleted += WorkerCompleted;
        }

        private void AcceptChanged(object sender, EventArgs e)
        {
            installButton.Enabled = acceptBox.Checked;
        }

        private void BrowseClick(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.SelectedPath = pathBox.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    pathBox.Text = dialog.SelectedPath;
                }
            }
        }

        private void InstallClick(object sender, EventArgs e)
        {
            if (!acceptBox.Checked)
            {
                MessageBox.Show(this, "请先阅读并同意许可证与第三方组件声明。", "许可协议", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            string target;
            try
            {
                target = Program.NormalizeTarget(pathBox.Text);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "安装路径", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            if (File.Exists(Path.Combine(target, "LyricsSubtitle.exe")))
            {
                DialogResult result = MessageBox.Show(
                    this,
                    "目标目录中已经存在歌词打轴，是否覆盖安装？",
                    "覆盖安装",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Question);
                if (result != DialogResult.Yes)
                {
                    return;
                }
            }

            installedTarget = target;
            SetBusy(true);
            progress.Value = 0;
            statusLabel.Text = "正在解压文件…";
            worker.RunWorkerAsync(new object[] { target, desktopBox.Checked, launchBox.Checked });
        }

        private void WorkerDoWork(object sender, DoWorkEventArgs e)
        {
            object[] parameters = (object[])e.Argument;
            try
            {
                e.Result = Program.Install(
                    (string)parameters[0],
                    (bool)parameters[1],
                    true,
                    delegate(int value) { worker.ReportProgress(value); });
            }
            catch (Exception ex)
            {
                e.Result = ex;
            }
        }

        private void WorkerProgressChanged(object sender, ProgressChangedEventArgs e)
        {
            progress.Value = Math.Max(0, Math.Min(100, e.ProgressPercentage));
        }

        private void WorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            SetBusy(false);
            if (e.Result is Exception)
            {
                statusLabel.Text = "安装失败";
                MessageBox.Show(this, ((Exception)e.Result).Message, "安装失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            List<string> warnings = (List<string>)e.Result;
            progress.Value = 100;
            statusLabel.Text = "安装完成";
            string message = Program.AppName + " 已安装到：\r\n" + installedTarget +
                "\r\n\r\n可以从桌面或开始菜单启动，也可以在 Windows 设置中卸载。";
            if (warnings != null && warnings.Count > 0)
            {
                message += "\r\n\r\n注意：\r\n" + String.Join("\r\n", warnings.ToArray());
            }
            MessageBox.Show(this, message, "安装完成", MessageBoxButtons.OK, MessageBoxIcon.Information);

            if (launchBox.Checked)
            {
                try
                {
                    Process.Start(Path.Combine(installedTarget, "LyricsSubtitle.exe"));
                }
                catch
                {
                }
            }
            Close();
        }

        private void SetBusy(bool busy)
        {
            pathBox.Enabled = !busy;
            browseButton.Enabled = !busy;
            acceptBox.Enabled = !busy;
            desktopBox.Enabled = !busy;
            launchBox.Enabled = !busy;
            installButton.Enabled = !busy && acceptBox.Checked;
        }
    }
}
