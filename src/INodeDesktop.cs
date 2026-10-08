using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Automation;

namespace ReInode {
    public static class Desktop {
        public const string Product = "\u66a8\u5357\u5927\u5b66\u6821\u56ed\u7f51";
        private delegate bool EnumProc(IntPtr h, IntPtr p);
        [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc callback, IntPtr p);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetClassName(IntPtr h, StringBuilder s, int n);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll", SetLastError=true)] private static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
        [DllImport("user32.dll")] private static extern bool CloseDesktop(IntPtr h);
        [DllImport("user32.dll", SetLastError=true)] private static extern bool SetThreadDesktop(IntPtr h);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern bool GetUserObjectInformation(IntPtr h, int index, StringBuilder s, int length, out int needed);
        [DllImport("user32.dll")] private static extern bool GetCursorPos(out POINT p);
        [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
        [DllImport("user32.dll")] private static extern IntPtr WindowFromPoint(POINT p);
        [DllImport("user32.dll",SetLastError=true)] private static extern uint SendInput(uint n, INPUT[] input, int size);
        [DllImport("user32.dll")] private static extern bool PostMessage(IntPtr h, uint message, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr h, int command);
        [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr h);
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll",EntryPoint="GetWindowLongW")] private static extern int GetWindowLong(IntPtr h,int index);
        [DllImport("user32.dll", SetLastError=true)] private static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int width, int height, uint flags);
        [DllImport("user32.dll")] private static extern IntPtr MonitorFromWindow(IntPtr h,uint flags);
        [DllImport("user32.dll")] private static extern bool GetMonitorInfo(IntPtr h,ref MONITORINFO info);
        [DllImport("user32.dll")] private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
        [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr h, out RECT r);
        [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr h,StringBuilder text,int length);
        [StructLayout(LayoutKind.Sequential)] private struct POINT { public int X,Y; public POINT(int x,int y){X=x;Y=y;} }
        [StructLayout(LayoutKind.Sequential)] private struct RECT { public int Left,Top,Right,Bottom; }
        [StructLayout(LayoutKind.Sequential)] private struct MONITORINFO { public int Size;public RECT Monitor,Work;public uint Flags; }
        [StructLayout(LayoutKind.Sequential)] private struct MOUSEINPUT { public int dx,dy; public uint data,flags,time; public UIntPtr extra; }
        [StructLayout(LayoutKind.Sequential)] private struct INPUT { public uint type; public MOUSEINPUT mouse; }

        public static bool Interactive() {
            IntPtr h = OpenInputDesktop(0, false, 1);
            if(h==IntPtr.Zero) return false;
            try { var name=new StringBuilder(256); int needed; return GetUserObjectInformation(h,2,name,512,out needed) && name.ToString()=="Default"; }
            finally { CloseDesktop(h); }
        }
        [ThreadStatic] private static DateTime actionDeadline;
        // PowerShell may already own COM windows. Bind a fresh thread before UIA creates any.
        private static T OnInputDesktop<T>(Func<T> operation) {
            T result=default(T); Exception failure=null;IntPtr desktop=IntPtr.Zero;
            var thread=new Thread(delegate(){
                try {
                    if(!Interactive()) throw new InvalidOperationException("DesktopLocked");
                    desktop=OpenInputDesktop(0,false,0x1ff);
                    if(desktop==IntPtr.Zero || !SetThreadDesktop(desktop)) throw new InvalidOperationException("InputDesktopBindFailed: "+Marshal.GetLastWin32Error());
                    SetThreadDpiAwarenessContext(new IntPtr(-4));
                    actionDeadline=DateTime.UtcNow.AddSeconds(10);
                    result=operation();
                } catch(Exception ex){failure=ex;}
            });
            thread.IsBackground=true;thread.SetApartmentState(ApartmentState.STA);thread.Start();
            if(!thread.Join(12000)) throw new TimeoutException("Desktop operation timed out; no late input is allowed.");
            if(desktop!=IntPtr.Zero) CloseDesktop(desktop);
            if(failure!=null) throw new InvalidOperationException(failure.Message,failure);
            return result;
        }
        private static string Class(IntPtr h) { var s=new StringBuilder(256); GetClassName(h,s,s.Capacity); return s.ToString(); }
        private static List<IntPtr> Windows() { var result=new List<IntPtr>(); EnumWindows(delegate(IntPtr h,IntPtr p){result.Add(h);return true;},IntPtr.Zero);return result; }
        private static uint Owner(IntPtr h) { uint id; GetWindowThreadProcessId(h,out id); return id; }
        public static string[] InspectClientWindows(int processId) {
            var result=new List<string>();
            foreach(var h in Windows()) if(Owner(h)==processId && IsWindowVisible(h)) {
                var title=new StringBuilder(256);GetWindowText(h,title,256);
                RECT r;GetWindowRect(h,out r);
                IntPtr above=WindowFromPoint(new POINT((r.Left+r.Right)/2,(r.Top+r.Bottom)/2));
                result.Add(h+" | "+Class(h)+" | "+title+" | bounds="+r.Left+","+r.Top+","+r.Right+","+r.Bottom+" | centerOwner="+Owner(above)+" centerClass="+Class(above));
            }
            return result.ToArray();
        }
        private static List<AutomationElement> TrayButtons() {
            var result=new List<AutomationElement>();
            foreach(var h in Windows()) {
                string cls=Class(h);
                if(cls!="Shell_TrayWnd" && cls!="Shell_SecondaryTrayWnd" && cls!="NotifyIconOverflowWindow" && cls!="TopLevelWindowForOverflowXamlIsland") continue;
                if(!IsWindowVisible(h)) continue;
                using(var p=Process.GetProcessById((int)Owner(h))) { if(p.ProcessName!="explorer") continue; }
                var root=AutomationElement.FromHandle(h);
                var buttons=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button));
                foreach(AutomationElement b in buttons) result.Add(b);
            }
            return result;
        }
        public static string[] InspectTray() {
            var result=new List<string>();
            foreach(var b in TrayButtons()) result.Add(b.Current.Name+" | "+b.Current.AutomationId+" | "+b.Current.ClassName+" | "+b.Current.BoundingRectangle);
            return result.ToArray();
        }
        public static string[] InspectMenus() {
            var result=new List<string>();
            foreach(var h in Windows()) if(IsWindowVisible(h)) {
                string cls=Class(h);
                if(cls.IndexOf("Menu",StringComparison.OrdinalIgnoreCase)>=0 || cls=="#32768" || cls.IndexOf("Popup",StringComparison.OrdinalIgnoreCase)>=0) {
                    uint pid=Owner(h);result.Add(h+" | "+cls+" | "+pid+" | "+Process.GetProcessById((int)pid).ProcessName);
                    var root=AutomationElement.FromHandle(h);
                    result.Add("ROOT: "+root.Current.Name+" "+root.Current.ControlType.ProgrammaticName);
                    foreach(AutomationElement a in root.FindAll(TreeScope.Descendants,Condition.TrueCondition)) result.Add(a.Current.ControlType.ProgrammaticName+" | "+a.Current.Name+" | "+a.Current.BoundingRectangle);
                }
            }
            return result.ToArray();
        }
        private static AutomationElement FindIcon() {
            var matches=new List<AutomationElement>();
            foreach(var b in TrayButtons()) {
                var name=b.Current.Name;
                if(b.Current.AutomationId=="NotifyItemIcon" && (name.IndexOf(Product,StringComparison.Ordinal)>=0 || name.IndexOf("iNode",StringComparison.OrdinalIgnoreCase)>=0) && !b.Current.IsOffscreen) matches.Add(b);
            }
            if(matches.Count!=1) throw new InvalidOperationException("TrayIconNotUniqueOrHidden: "+matches.Count);
            return matches[0];
        }
        public static bool Ready() { try{return OnInputDesktop(delegate(){FindIcon();return true;});}catch{return false;} }
        private static IntPtr FindPopup(int processId) {
            var found=new List<IntPtr>();
            foreach(var h in Windows()) if(IsWindowVisible(h) && Owner(h)==processId && Class(h)=="Qt5QWindowPopupDropShadowSaveBits") found.Add(h);
            if(found.Count>1) throw new InvalidOperationException("AmbiguousClientPopup");
            return found.Count==1?found[0]:IntPtr.Zero;
        }
        public static long OpenPopup(int processId) {return OnInputDesktop(delegate(){return OpenPopupCore(processId);});}
        public static string DescribePopup(long expected,int processId) {return OnInputDesktop(delegate(){
            IntPtr foreground=GetForegroundWindow();
            return "expected="+expected+" current="+FindPopup(processId)+" foreground="+foreground+" foregroundOwner="+Owner(foreground);
        });}
        public static string[] ProbePopupLifetime(int processId) {return OnInputDesktop(delegate(){
            var samples=new List<string>();
            long handle=OpenPopupCore(processId);
            try {
                for(int i=0;i<16;i++) {
                    IntPtr current=FindPopup(processId),foreground=GetForegroundWindow();
                    samples.Add("ms="+(i*200)+" expected="+handle+" current="+current+" foreground="+foreground+" foregroundOwner="+Owner(foreground));
                    if(current==IntPtr.Zero)break;
                    Thread.Sleep(200);
                }
            } finally {DismissPopupCore(handle,processId);}
            return samples.ToArray();
        });}
        private static long OpenPopupCore(int processId) {
            SetThreadDpiAwarenessContext(new IntPtr(-4));
            if(!Interactive()) throw new InvalidOperationException("DesktopLocked");
            IntPtr popup=FindPopup(processId);
            if(popup!=IntPtr.Zero) return PreparePopup(popup,processId);
            // A tray click may be consumed during activation. Retry only opening,
            // never an exit command, and resolve the icon again before each input.
            for(int attempt=0;attempt<2;attempt++) {
                var icon=FindIcon();var r=icon.Current.BoundingRectangle;
                Click((int)(r.Left+r.Width/2),(int)(r.Top+r.Height/2),true,(uint)icon.Current.ProcessId);
                for(int i=0;i<30;i++){Thread.Sleep(100);popup=FindPopup(processId);if(popup!=IntPtr.Zero)return PreparePopup(popup,processId);}
            }
            throw new InvalidOperationException("ClientPopupUnavailable: "+String.Join("; ",InspectClientWindows(processId)));
        }
        private static long PreparePopup(IntPtr popup,int processId) {
            if(FindPopup(processId)!=popup)throw new InvalidOperationException("PopupChanged");
            Thread.Sleep(250);
            if(FindPopup(processId)!=popup)throw new InvalidOperationException("PopupChanged");
            RECT r;
            if(!GetWindowRect(popup,out r))throw new InvalidOperationException("PopupBoundsUnavailable");
            if(Owner(WindowFromPoint(new POINT((r.Left+r.Right)/2,(r.Top+r.Bottom)/2)))!=processId) {
                // IME overlays can stay above even a topmost popup. Move only the
                // owned transient menu into its monitor's work area, then OCR again.
                var monitor=new MONITORINFO();monitor.Size=Marshal.SizeOf(typeof(MONITORINFO));
                if(!GetMonitorInfo(MonitorFromWindow(popup,2),ref monitor))throw new InvalidOperationException("PopupMonitorUnavailable");
                int[] position=PopupPosition(monitor.Work.Left,monitor.Work.Top,monitor.Work.Right,monitor.Work.Bottom,r.Right-r.Left,r.Bottom-r.Top);
                int x=position[0],y=position[1];
                if(!SetWindowPos(popup,IntPtr.Zero,x,y,0,0,0x15))throw new InvalidOperationException("PopupMoveFailed");
                Thread.Sleep(200);
            }
            return popup.ToInt64();
        }
        public static int[] PopupPosition(int left,int top,int right,int bottom,int width,int height) {
            if(width<30 || height<30 || width>1200 || height>800 || right-left<width || bottom-top<height)
                throw new InvalidOperationException("UnexpectedPopupGeometry");
            return new int[]{left+(right-left-width)/2,top+(bottom-top-height)/2};
        }
        public static string CapturePopup(long handle,int processId,string path) {return OnInputDesktop(delegate(){return CapturePopupCore(handle,processId,path);});}
        private static string CapturePopupCore(long handle,int processId,string path) {
            if(FindPopup(processId)!=new IntPtr(handle)) throw new InvalidOperationException("PopupChanged");
            return CaptureWindowCore(handle,processId,path);
        }
        private static string CaptureWindowCore(long handle,int processId,string path) {
            SetThreadDpiAwarenessContext(new IntPtr(-4));
            IntPtr h=new IntPtr(handle);RECT r;
            if(!Interactive() || Owner(h)!=processId || !IsWindowVisible(h) || !GetWindowRect(h,out r)) throw new InvalidOperationException("WindowChanged");
            int w=r.Right-r.Left, height=r.Bottom-r.Top;
            if(w<30 || height<30 || w>1200 || height>800) throw new InvalidOperationException("UnexpectedWindowSize");
            if(Owner(WindowFromPoint(new POINT((r.Left+r.Right)/2,(r.Top+r.Bottom)/2)))!=processId) throw new InvalidOperationException("PopupOccluded: "+String.Join("; ",InspectClientWindows(processId)));
            using(var bitmap=new System.Drawing.Bitmap(w,height)) {
                using(var graphics=System.Drawing.Graphics.FromImage(bitmap)) graphics.CopyFromScreen(r.Left,r.Top,0,0,new System.Drawing.Size(w,height));
                using(var scaled=new System.Drawing.Bitmap(w*3,height*3)) {
                    using(var graphics=System.Drawing.Graphics.FromImage(scaled)) {
                        graphics.InterpolationMode=System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                        graphics.DrawImage(bitmap,0,0,w*3,height*3);
                    }
                    scaled.Save(path,System.Drawing.Imaging.ImageFormat.Png);
                }
            }
            return r.Left+","+r.Top+","+w+","+height;
        }
        private static IntPtr FindConfirmation(int processId) {
            var found=new List<IntPtr>();
            foreach(var h in Windows()) if(Owner(h)==processId && IsWindowVisible(h) && Class(h)=="Qt5QWindowIcon") {
                RECT r;var title=new StringBuilder(256);GetWindowText(h,title,256);
                if(title.ToString()==Product && GetWindowRect(h,out r) && r.Bottom-r.Top<=500)found.Add(h);
            }
            if(found.Count>1)throw new InvalidOperationException("AmbiguousConfirmationWindow");
            return found.Count==1?found[0]:IntPtr.Zero;
        }
        public static long FindExitConfirmation(int processId) {return OnInputDesktop(delegate(){return FindConfirmation(processId).ToInt64();});}
        public static string CaptureConfirmation(long handle,int processId,string path) {return OnInputDesktop(delegate(){
            if(FindConfirmation(processId)!=new IntPtr(handle))throw new InvalidOperationException("ConfirmationChanged");
            return CaptureWindowCore(handle,processId,path);
        });}
        private static List<IntPtr> FindStatusWindows(int processId) {
            var found=new List<IntPtr>();
            foreach(var h in Windows()) if(Owner(h)==processId && Class(h)=="Qt5QWindowIcon") {
                RECT r;var title=new StringBuilder(256);GetWindowText(h,title,256);
                if(title.ToString()==Product && GetWindowRect(h,out r) && r.Bottom-r.Top>500 && r.Bottom-r.Top<900)found.Add(h);
            }
            return found;
        }
        public static string CaptureClientStatus(int processId,string path) {return CaptureClientStatus(processId,path,false);}
        public static string CaptureClientStatus(int processId,string path,bool revealFromTray) {return OnInputDesktop(delegate(){
            var found=FindStatusWindows(processId);
            if(found.Count==0 && revealFromTray) {
                var icon=FindIcon();var r=icon.Current.BoundingRectangle;
                int x=(int)(r.Left+r.Width/2),y=(int)(r.Top+r.Height/2);
                Click(x,y,false,(uint)icon.Current.ProcessId);
                Thread.Sleep(60);
                var current=FindIcon().Current.BoundingRectangle;
                if(current!=r)throw new InvalidOperationException("TrayIconMoved");
                Click(x,y,false,(uint)icon.Current.ProcessId);
                for(int i=0;i<20;i++){Thread.Sleep(100);found=FindStatusWindows(processId);if(found.Count!=0)break;}
            }
            if(found.Count!=1)throw new InvalidOperationException("ClientStatusWindowNotUnique");
            ShowWindow(found[0],9);SetForegroundWindow(found[0]);Thread.Sleep(200);
            if(!revealFromTray)return CaptureWindowCore(found[0].ToInt64(),processId,path);
            bool wasTopmost=(GetWindowLong(found[0],-20)&8)!=0;
            try {
                if(!SetWindowPos(found[0],new IntPtr(-1),0,0,0,0,0x13))throw new InvalidOperationException("StatusRevealFailed");
                Thread.Sleep(200);
                return CaptureWindowCore(found[0].ToInt64(),processId,path);
            } finally {if(!wasTopmost)SetWindowPos(found[0],new IntPtr(-2),0,0,0,0,0x13);}
        });}
        public static void ConfirmExit(long handle,int processId,string expectedBounds,int x,int y) {OnInputDesktop(delegate(){
            IntPtr h=new IntPtr(handle);RECT r;
            if(FindConfirmation(processId)!=h || !GetWindowRect(h,out r))throw new InvalidOperationException("ConfirmationChanged");
            if(expectedBounds!=r.Left+","+r.Top+","+(r.Right-r.Left)+","+(r.Bottom-r.Top))throw new InvalidOperationException("ConfirmationMoved");
            if(x<=0 || y<=0 || x>=r.Right-r.Left || y>=r.Bottom-r.Top)throw new InvalidOperationException("InvalidConfirmationTarget");
            Click(r.Left+x,r.Top+y,false,(uint)processId);return true;
        });}
        public static void ClickPopupText(long handle,int processId,string expectedBounds,int x,int y) {OnInputDesktop(delegate(){ClickPopupTextCore(handle,processId,expectedBounds,x,y,true);return true;});}
        public static void AimPopupText(long handle,int processId,string expectedBounds,int x,int y) {OnInputDesktop(delegate(){ClickPopupTextCore(handle,processId,expectedBounds,x,y,false);return true;});}
        private static void ClickPopupTextCore(long handle,int processId,string expectedBounds,int x,int y,bool invoke) {
            IntPtr h=new IntPtr(handle); RECT r;
            if(!Interactive() || FindPopup(processId)!=h || !GetWindowRect(h,out r)) throw new InvalidOperationException("PopupChanged");
            if(expectedBounds!=r.Left+","+r.Top+","+(r.Right-r.Left)+","+(r.Bottom-r.Top)) throw new InvalidOperationException("PopupMoved");
            if(x<=0 || y<=0 || x>=r.Right-r.Left || y>=r.Bottom-r.Top) throw new InvalidOperationException("InvalidTextBounds");
            Click(r.Left+x,r.Top+y,false,(uint)processId,invoke);
        }
        public static void DismissPopup(long handle,int processId) {
            OnInputDesktop(delegate(){DismissPopupCore(handle,processId);return true;});
        }
        private static void DismissPopupCore(long handle,int processId) {
            IntPtr h=new IntPtr(handle);
            if(FindPopup(processId)==h) { PostMessage(h,0x0100,new IntPtr(27),IntPtr.Zero);PostMessage(h,0x0101,new IntPtr(27),IntPtr.Zero); }
        }
        private static void Click(int x,int y,bool right,uint expectedOwner,bool invoke=true) {
            if(DateTime.UtcNow>actionDeadline) throw new TimeoutException("Input deadline expired.");
            SetThreadDpiAwarenessContext(new IntPtr(-4));
            if(!Interactive()) throw new InvalidOperationException("DesktopLocked");
            IntPtr under=WindowFromPoint(new POINT(x,y));
            if(Owner(under)!=expectedOwner) throw new InvalidOperationException("TargetOccludedOrChanged: expected="+expectedOwner+" actual="+Owner(under)+" class="+Class(under)+" point="+x+","+y);
            int left=GetSystemMetrics(76),top=GetSystemMetrics(77),width=GetSystemMetrics(78),height=GetSystemMetrics(79);
            if(width<=0 || height<=0) throw new InvalidOperationException("DesktopGeometryUnavailable");
            INPUT move=new INPUT();move.mouse.flags=0xc001;
            move.mouse.dx=(int)(((long)(x-left)*65536+32768)/width);
            move.mouse.dy=(int)(((long)(y-top)*65536+32768)/height);
            if(SendInput(1,new INPUT[]{move},Marshal.SizeOf(typeof(INPUT)))!=1) throw new InvalidOperationException("PointerInputRejected: "+Marshal.GetLastWin32Error());
            Thread.Sleep(30);POINT actual;
            bool got=GetCursorPos(out actual);uint actualOwner=Owner(WindowFromPoint(actual));
            if(!got || Math.Abs(actual.X-x)>2 || Math.Abs(actual.Y-y)>2 || actualOwner!=expectedOwner) throw new InvalidOperationException("PointerDidNotReachTarget: requested="+x+","+y+" observed="+actual.X+","+actual.Y+" read="+got+" owner="+actualOwner+" expectedOwner="+expectedOwner+" screen="+left+","+top+","+width+","+height);
            if(!invoke)return;
            INPUT down=new INPUT();down.mouse.flags=right?0x0008u:0x0002u;
            INPUT up=new INPUT();up.mouse.flags=right?0x0010u:0x0004u;
            if(SendInput(2,new INPUT[]{down,up},Marshal.SizeOf(typeof(INPUT)))!=2) throw new InvalidOperationException("InputRejected: Win32="+Marshal.GetLastWin32Error()+" size="+Marshal.SizeOf(typeof(INPUT)));
        }
        public static void HideClientWindow(int processId) {
            OnInputDesktop(delegate(){foreach(var h in Windows()) if(Owner(h)==processId && IsWindowVisible(h) && Class(h)!="#32768") ShowWindow(h,0);return true;});
        }
        public static void CloseClientWindows(int processId) {
            OnInputDesktop(delegate(){
                foreach(var h in Windows()) if(Owner(h)==processId && Class(h)!="#32768")
                    PostMessage(h,0x0010,IntPtr.Zero,IntPtr.Zero);
                return true;
            });
        }
        public static void LaunchShortcut(string shortcut,string workingDirectory) {
            OnInputDesktop(delegate(){
                var start=new ProcessStartInfo(shortcut);
                start.UseShellExecute=true;start.WorkingDirectory=workingDirectory;start.WindowStyle=ProcessWindowStyle.Normal;
                using(var process=Process.Start(start)) { }
                return true;
            });
        }
    }
}
