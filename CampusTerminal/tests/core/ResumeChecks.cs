// SPDX-License-Identifier: GPL-3.0-or-later
using System.Reflection;
using System.Text.Json.Nodes;

namespace CampusAuth;

/// <summary>
/// Regression checks for the resume-ownership right: a previous CampusTerminal
/// session may be taken over from a resident iNode only when this process still
/// owns it, and only on the adapter that reached online.
/// </summary>
internal static class ResumeChecks
{
    private const BindingFlags Flags = BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public;

    public static void Run(Action<bool, string> check)
    {
        var adapterA = Guid.NewGuid();
        var adapterB = Guid.NewGuid();
        check(GuiHost.ResumeRightHeld(true, adapterA, adapterA, true, false),
            "A verified session holds the resume right on its adapter");
        check(!GuiHost.ResumeRightHeld(true, adapterA, adapterB, true, false),
            "A different adapter loses the resume right");
        check(!GuiHost.ResumeRightHeld(true, adapterA, adapterA, false, false),
            "Disabled auto-reconnect loses the resume right");
        check(!GuiHost.ResumeRightHeld(true, adapterA, adapterA, true, true),
            "An in-flight handback loses the resume right");
        check(!GuiHost.ResumeRightHeld(false, adapterA, adapterA, true, false),
            "No session means no resume right");
        check(GuiHost.ResumeNeedsTakeover(true, true, true),
            "Resume takeover needs the request, the right and a resident original");
        check(!GuiHost.ResumeNeedsTakeover(false, true, true),
            "A normal retry never spends the resume right");
        check(!GuiHost.ResumeNeedsTakeover(true, false, true),
            "A lost right never takes over");
        check(!GuiHost.ResumeNeedsTakeover(true, true, false),
            "No takeover when no official client is resident");
        check(GuiHost.ResumeRightLostAfterSubmit(false, false, false),
            "A lost right cancels the submitted takeover");
        check(GuiHost.ResumeRightLostAfterSubmit(true, true, false),
            "A cancelled request cancels the submitted takeover");
        check(GuiHost.ResumeRightLostAfterSubmit(true, false, true),
            "An alternative network cancels the submitted takeover");
        check(!GuiHost.ResumeRightLostAfterSubmit(true, false, false),
            "A held right and no alternative keeps the takeover");

        var owned = typeof(GuiHost).GetField("resumeOwnedSession", Flags)!;
        var ownedAdapter = typeof(GuiHost).GetField("resumeOwnedAdapter", Flags)!;
        var auto = typeof(GuiHost).GetField("autoReconnect", Flags)!;
        var campus = typeof(GuiHost).GetField("campusAdapter", Flags)!;
        var phase = typeof(GuiHost).GetField("phase", Flags)!;
        var note = typeof(GuiHost).GetMethod("Note", Flags)!;
        var clear = typeof(GuiHost).GetMethod("ClearOwnedSession", Flags)!;
        var heldFor = typeof(GuiHost).GetMethod("ResumeRightHeldFor", Flags)!;
        var configure = typeof(GuiHost).GetMethod("Configure", Flags)!;
        var previous = (Owned: owned.GetValue(null), Adapter: ownedAdapter.GetValue(null),
            Auto: auto.GetValue(null), Campus: campus.GetValue(null), Phase: phase.GetValue(null));
        try
        {
            campus.SetValue(null, adapterA);
            owned.SetValue(null, false);
            ownedAdapter.SetValue(null, Guid.Empty);
            auto.SetValue(null, true);
            phase.SetValue(null, "connecting");
            note.Invoke(null, ["TwoCampusRoundsPassed"]);
            check((bool)owned.GetValue(null)!, "Entering online records the resume right");
            check((Guid)ownedAdapter.GetValue(null)! == adapterA,
                "The resume right names the adapter that reached online");
            note.Invoke(null, ["AuthenticationRejected"]);
            check((bool)owned.GetValue(null)!, "An authentication rejection keeps the resume right");
            note.Invoke(null, ["TwoCampusRoundsUnavailable"]);
            check((bool)owned.GetValue(null)!, "A campus outage keeps the resume right");
            phase.SetValue(null, "error");
            check((bool)heldFor.Invoke(null, [adapterA])!,
                "The core reports a held right after the capped session failed");
            configure.Invoke(null, [1, new JsonObject
            {
                ["options"] = new JsonObject { ["adapterId"] = adapterB.ToString(), ["autoReconnect"] = true }
            }]);
            check(!(bool)owned.GetValue(null)!, "Configuring another adapter clears the resume right");
            note.Invoke(null, ["TwoCampusRoundsPassed"]);
            check((bool)owned.GetValue(null)!, "A later verified session can own the right again");
            configure.Invoke(null, [2, new JsonObject
            {
                ["options"] = new JsonObject { ["autoReconnect"] = false }
            }]);
            check(!(bool)owned.GetValue(null)!, "Disabling auto-reconnect clears the resume right");
            owned.SetValue(null, true);
            ownedAdapter.SetValue(null, adapterA);
            clear.Invoke(null, ["ManualDisconnect"]);
            check(!(bool)owned.GetValue(null)!, "A manual disconnect clears the resume right");
        }
        finally
        {
            owned.SetValue(null, previous.Owned);
            ownedAdapter.SetValue(null, previous.Adapter);
            auto.SetValue(null, previous.Auto);
            campus.SetValue(null, previous.Campus);
            phase.SetValue(null, previous.Phase);
        }
    }
}
