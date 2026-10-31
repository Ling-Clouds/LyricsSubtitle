using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using Microsoft.Win32;

namespace LyricsSubtitleUninstall
{
    internal static class Program
    {
        private const string AppName = "歌词打轴";
        private const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\LyricsSubtitle";

        [STAThread]
        private static int Main(string[] args)
        {
            bool silent = HasArg(args, "--silent");
            string directory = ArgValue(args, "--dir");
            if (String.IsNullOrEmpty(directory))
            {
                directory = Path.GetDirectoryName(Application.ExecutablePath);
            }

            if (String.IsNullOrEmpty(directory))
            {
                return 2;
            }
            directory = Path.GetFullPath(directory);
            if (!Directory.Exists(directory))
            {
                return 2;
            }

            if (!silent)
            {
                Application.EnableVisualStyles();
                DialogResult result = MessageBox.Show(
                    "确定要卸载 " + AppName + " 吗？\r\n\r\n安装目录：\r\n" + directory,
                    "卸载 " + AppName,
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Question);
                if (result != DialogResult.Yes)
                {
                    return 1;
                }
            }

            RemoveShortcuts();
            RemoveRegistry();
            RemoveApplicationFiles(directory);
            ScheduleDelete(directory);
            return 0;
        }

        private static void RemoveShortcuts()
        {
            try
            {
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string link = Path.Combine(desktop, AppName + ".lnk");
                if (File.Exists(link))
                {
                    File.Delete(link);
                }
            }
            catch
            {
            }

            try
            {
                string startFolder = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    @"Microsoft\Windows\Start Menu\Programs",
                    AppName);
                if (Directory.Exists(startFolder))
                {
                    Directory.Delete(startFolder, true);
                }
            }
            catch
            {
            }
        }

        private static void RemoveRegistry()
        {
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(UninstallKey, false);
            }
            catch
            {
            }
        }

        private static void RemoveApplicationFiles(string directory)
        {
            foreach (string path in Directory.GetFileSystemEntries(directory))
            {
                if (String.Equals(Path.GetFileName(path), "Uninstall.exe", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                try
                {
                    if (Directory.Exists(path))
                    {
                        Directory.Delete(path, true);
                    }
                    else
                    {
                        File.Delete(path);
                    }
                }
                catch
                {
                }
            }
        }

        private static void ScheduleDelete(string directory)
        {
            try
            {
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = "cmd.exe";
                info.Arguments = "/c timeout /t 2 /nobreak >nul & rmdir /s /q \"" + directory + "\"";
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                Process.Start(info);
            }
            catch
            {
            }
        }

        private static bool HasArg(string[] args, string name)
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

        private static string ArgValue(string[] args, string name)
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
}
