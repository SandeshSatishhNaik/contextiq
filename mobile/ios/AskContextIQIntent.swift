// Siri / Shortcuts integration via App Intents (iOS 17+).
// NOT BUILT OR TESTED in this project's environment (needs Xcode on a Mac). Drop into a SwiftUI app target.
// "Hey Siri, ask ContextIQ can I return my headphones" → calls the ContextIQ voice endpoint → Siri speaks the answer.
// Money actions are refused by the server for voice; this intent is read-only by design.
import AppIntents
import Foundation

struct AskContextIQIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask ContextIQ"
    static var description = IntentDescription("Ask about a payment, refund, bill or budget.")
    static var openAppWhenRun = false

    @Parameter(title: "Question") var question: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let base = UserDefaults.standard.string(forKey: "contextiq_url") ?? "https://YOUR-PUBLIC-URL"
        let token = UserDefaults.standard.string(forKey: "contextiq_voice_token") ?? ""
        var req = URLRequest(url: URL(string: "\(base)/api/voice")!)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(token, forHTTPHeaderField: "X-Voice-Token")
        req.setValue("alex", forHTTPHeaderField: "X-User-Id")
        req.httpBody = try JSONEncoder().encode(["text": question])
        let (data, _) = try await URLSession.shared.data(for: req)
        let speech = (try? JSONDecoder().decode([String: String].self, from: data))?["speech"]
            ?? "Sorry, I couldn't reach ContextIQ."
        return .result(dialog: IntentDialog(stringLiteral: speech))
    }
}

struct ContextIQShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskContextIQIntent(),
                    phrases: ["Ask \(.applicationName)", "Ask \(.applicationName) a question"],
                    shortTitle: "Ask ContextIQ", systemImageName: "bubble.left.and.text.bubble.right")
    }
}
