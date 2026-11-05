import AppKit
import Darwin
import Dispatch
import SignDesktopCore

@main
@MainActor
enum SignDesktopApp {
    static func main() {
        signal(SIGPIPE, SIG_IGN)
        let application = NSApplication.shared
        let delegate = DesktopApplication()
        application.setActivationPolicy(.accessory)
        application.delegate = delegate
        application.run()
        withExtendedLifetime(delegate) {}
    }
}

@MainActor
final class DesktopApplication: NSObject, NSApplicationDelegate {
    private var item: NSStatusItem?
    private var configuration: AppConfiguration?
    private var log: BoundedLog?
    private var process: Process?
    private var input: Pipe?
    private var output: Pipe?
    private var diagnostics: Pipe?
    private var outputReader: (any DispatchSourceRead)?
    private var diagnosticReader: (any DispatchSourceRead)?
    private var exitStatus: Int32?
    private var exitWasExpected = false
    private var framing = LineFramer()
    private var lifecycle = ProcessLifecycle()
    private var menuState = MenuState()
    private var runtimeError: String?
    private var recoveryWarning: String?
    private var waitingForQuit = false
    private var observers: [NSObjectProtocol] = []
    private let notifications = NotificationCoordinator(client: NativeNotifications())

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item?.button?.image = MenuBarIcon.make()
        item?.button?.imagePosition = .imageOnly
        item?.button?.setAccessibilityLabel("My Sign")
        item?.button?.toolTip = "Sign image workflow"
        notifications.onStatusChange = { [weak self] in self?.render() }
        let workspace = NSWorkspace.shared.notificationCenter
        observers.append(workspace.addObserver(
            forName: NSWorkspace.willSleepNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.sleep() }
        })
        observers.append(workspace.addObserver(
            forName: NSWorkspace.didWakeNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.wake() }
        })
        do {
            configuration = try AppConfiguration(info: Bundle.main.infoDictionary ?? [:])
            if let configuration { log = BoundedLog(directory: configuration.logDirectory) }
            perform(lifecycle.requestStart())
        } catch {
            runtimeError = error.localizedDescription
        }
        render()
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard process != nil else { return .terminateNow }
        waitingForQuit = true
        perform(lifecycle.requestQuit())
        render()
        return .terminateLater
    }

    func applicationWillTerminate(_ notification: Notification) {
        for observer in observers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
    }

    private func start() {
        guard let configuration, lifecycle.session == nil,
              !lifecycle.isSleeping, !lifecycle.isQuitting else { return }
        let session = UUID().uuidString
        let child = Process()
        let childInput = Pipe()
        let childOutput = Pipe()
        let childDiagnostics = Pipe()
        child.executableURL = configuration.executable
        child.arguments = ["workflow", "desktop", "--config", configuration.configuration.path]
        child.standardInput = childInput
        child.standardOutput = childOutput
        child.standardError = childDiagnostics
        child.terminationHandler = { [weak self] exited in
            let status = exited.terminationStatus
            Task { @MainActor in self?.exited(session: session, status: status) }
        }
        process = child
        input = childInput
        output = childOutput
        diagnostics = childDiagnostics
        lifecycle.didStart(session)
        menuState = MenuState()
        framing = LineFramer()
        exitStatus = nil
        exitWasExpected = false
        runtimeError = nil
        do {
            try child.run()
            outputReader = reader(childOutput.fileHandleForReading, stream: .stdout, session: session)
            diagnosticReader = reader(childDiagnostics.fileHandleForReading, stream: .stderr, session: session)
            // Only Python keeps the peer ends; parent death must reach the child's stdin as EOF.
            try? childInput.fileHandleForReading.close()
            try? childOutput.fileHandleForWriting.close()
            try? childDiagnostics.fileHandleForWriting.close()
        } catch {
            runtimeError = "Could not start the workflow: \(error.localizedDescription)"
            closePipes()
            process = nil
            _ = lifecycle.didClose(.stdout, session: session)
            _ = lifecycle.didClose(.stderr, session: session)
            perform(lifecycle.didExit(session))
        }
        render()
    }

    private func reader(_ handle: FileHandle, stream: ChildStream, session: String) -> any DispatchSourceRead {
        let source = DispatchSource.makeReadSource(fileDescriptor: handle.fileDescriptor, queue: .main)
        source.setEventHandler { [weak self] in
            // The source's main queue preserves byte/EOF order without asynchronous actor handoffs.
            MainActor.assumeIsolated {
                guard let self, self.lifecycle.session == session else { return }
                let bytes = handle.availableData
                if bytes.isEmpty {
                    if stream == .stdout { self.outputReader?.cancel() }
                    else { self.diagnosticReader?.cancel() }
                }
                if stream == .stdout { self.receive(bytes, session: session) }
                else { self.record(bytes, session: session) }
            }
        }
        source.resume()
        return source
    }

    private func receive(_ bytes: Data, session: String) {
        guard lifecycle.session == session else { return }
        if bytes.isEmpty {
            var effects: [LifecycleEffect] = []
            do { if !lifecycle.stopRequested { try framing.finish() } }
            catch {
                runtimeError = error.localizedDescription
                effects = lifecycle.requestStop()
            }
            effects += lifecycle.didClose(.stdout, session: session)
            finishTransition(effects)
            return
        }
        do {
            for record in try framing.append(bytes) {
                switch try DesktopMessage.decode(record) {
                case .view(let view):
                    menuState.receive(view)
                    render()
                case .notification(let notification):
                    notify(notification, session: session)
                }
            }
        } catch {
            runtimeError = error.localizedDescription
            perform(lifecycle.requestStop())
            render()
        }
    }

    private func notify(_ notification: DesktopNotification, session: String) {
        guard lifecycle.canInteract(with: session) else { return }
        menuState.beginNotification(notification.id)
        render()
        notifications.send(notification, isCurrent: { [weak self] in
            self?.lifecycle.canInteract(with: session) == true
        }) { [weak self] acknowledgment in
            guard let self, self.lifecycle.canInteract(with: session) else { return }
            if self.send(acknowledgment, session: session) {
                self.menuState.finishNotification(notification.id)
                self.render()
            }
        }
    }

    @discardableResult
    private func send<T: Encodable>(_ record: T, session: String) -> Bool {
        guard lifecycle.canInteract(with: session), let input else { return false }
        do {
            try input.fileHandleForWriting.write(contentsOf: encodeRecord(record))
            return true
        } catch {
            runtimeError = "Could not send the workflow action: \(error.localizedDescription)"
            perform(lifecycle.requestStop())
            render()
            return false
        }
    }

    private func record(_ bytes: Data, session: String) {
        guard lifecycle.session == session else { return }
        if bytes.isEmpty {
            finishTransition(lifecycle.didClose(.stderr, session: session))
            return
        }
        do { try log?.append(bytes) }
        catch {
            runtimeError = "Could not write diagnostic logs: \(error.localizedDescription)"
            render()
        }
    }

    private func exited(session: String, status: Int32) {
        guard lifecycle.session == session else { return }
        exitStatus = status
        exitWasExpected = lifecycle.stopRequested
        finishTransition(lifecycle.didExit(session))
    }

    private func finishTransition(_ effects: [LifecycleEffect]) {
        if lifecycle.session == nil && process != nil {
            closePipes()
            process = nil
            if let status = exitStatus, !exitWasExpected && runtimeError == nil {
                runtimeError = "Workflow stopped (exit \(status)). See diagnostic logs, then restart the workflow."
            }
        }
        perform(effects)
        render()
    }

    private func closePipes() {
        outputReader?.cancel()
        diagnosticReader?.cancel()
        outputReader = nil
        diagnosticReader = nil
        try? input?.fileHandleForWriting.close()
        try? output?.fileHandleForReading.close()
        try? diagnostics?.fileHandleForReading.close()
        input = nil
        output = nil
        diagnostics = nil
    }

    private func perform(_ effects: [LifecycleEffect]) {
        for effect in effects {
            switch effect {
            case .start: start()
            case .terminate(let session):
                if lifecycle.session == session, process?.isRunning == true { process?.terminate() }
            case .scheduleDrainDeadline(let session):
                DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in
                    MainActor.assumeIsolated {
                        guard let self else { return }
                        self.finishTransition(self.lifecycle.drainDeadlineExpired(session))
                    }
                }
            case .drainTimedOut:
                recoveryWarning = "The workflow exited with an output stream still open. A producer may still be "
                    + "running. Confirm related processes have stopped before manually removing workflow locks."
                if let recoveryWarning { try? log?.append(Data((recoveryWarning + "\n").utf8)) }
            case .quit:
                if waitingForQuit { NSApplication.shared.reply(toApplicationShouldTerminate: true) }
                else { NSApplication.shared.terminate(nil) }
            }
        }
    }

    private func sleep() {
        perform(lifecycle.requestSleep())
        render()
    }

    private func wake() {
        perform(lifecycle.requestWake())
        render()
    }

    @objc private func upload() { act(.upload) }
    @objc private func check() { act(.check) }

    private func act(_ action: MenuAction) {
        guard let session = lifecycle.session, lifecycle.canInteract(with: session),
              let record = menuState.take(action) else { return }
        render()
        send(record, session: session)
    }

    @objc private func testNotification() {
        let request = DesktopNotification(
            id: "test-\(UUID().uuidString)", kind: .updateAvailable,
            title: "My Sign notification test", body: "Notifications are working. No image will be uploaded."
        )
        notifications.send(request, isCurrent: { [weak self] in
            self?.lifecycle.isQuitting == false
        }) { _ in }
    }

    @objc private func restart() { perform(lifecycle.requestStart()) }

    @objc private func openSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func openLogs() {
        if let configuration { NSWorkspace.shared.open(configuration.logDirectory) }
    }

    @objc private func quit() { NSApplication.shared.terminate(nil) }

    private func render() {
        let menu = NSMenu()
        menu.autoenablesItems = false
        let view = menuState.view
        let status: String
        if lifecycle.isQuitting { status = "Stopping workflow…" }
        else if lifecycle.isSleeping { status = "Paused while the Mac sleeps." }
        else if exitStatus != nil && process != nil { status = "Finishing workflow cleanup…" }
        else if process == nil { status = "Workflow stopped." }
        else { status = view?.message ?? "Starting workflow…" }
        addStatus(status, to: menu)
        if let lastCheck = view?.lastCheck { addStatus("Last successful check: \(displayDate(lastCheck))", to: menu) }
        if let result = view?.lastResult { addStatus(result, to: menu) }
        if let error = view?.error { addStatus(error, to: menu) }
        if let runtimeError { addStatus(runtimeError, to: menu) }
        if let recoveryWarning { addStatus(recoveryWarning, to: menu) }
        if let error = notifications.lastError { addStatus("Notifications: \(error)", to: menu) }
        menu.addItem(.separator())
        let active = lifecycle.session.map { lifecycle.canInteract(with: $0) } ?? false
        addAction(
            view?.retained == true ? "Upload retained image" : "Upload", selector: #selector(upload),
            enabled: active && menuState.canUpload, to: menu
        )
        addAction("Check now", selector: #selector(check), enabled: active && menuState.canCheck, to: menu)
        addAction(
            "Restart workflow", selector: #selector(restart),
            enabled: process == nil && !lifecycle.isSleeping && !lifecycle.isQuitting && configuration != nil, to: menu
        )
        menu.addItem(.separator())
        addAction("Test notification", selector: #selector(testNotification), enabled: !lifecycle.isQuitting, to: menu)
        addAction("Notification settings…", selector: #selector(openSettings), enabled: true, to: menu)
        addAction("Open diagnostic logs…", selector: #selector(openLogs), enabled: configuration != nil, to: menu)
        menu.addItem(.separator())
        addAction("Quit My Sign", selector: #selector(quit), enabled: !lifecycle.isQuitting, to: menu)
        item?.menu = menu
        item?.button?.toolTip = status
    }

    private func addStatus(_ text: String, to menu: NSMenu) {
        let title = text.count > 160 ? String(text.prefix(157)) + "…" : text
        let entry = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        entry.isEnabled = false
        entry.toolTip = text
        menu.addItem(entry)
    }

    private func addAction(_ title: String, selector: Selector, enabled: Bool, to menu: NSMenu) {
        let entry = NSMenuItem(title: title, action: selector, keyEquivalent: "")
        entry.target = self
        entry.isEnabled = enabled
        menu.addItem(entry)
    }

    private func displayDate(_ value: String) -> String {
        let format = ISO8601DateFormatter()
        format.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = format.date(from: value)
        if date == nil {
            format.formatOptions = [.withInternetDateTime]
            date = format.date(from: value)
        }
        guard let date else { return value }
        return DateFormatter.localizedString(from: date, dateStyle: .short, timeStyle: .short)
    }
}
