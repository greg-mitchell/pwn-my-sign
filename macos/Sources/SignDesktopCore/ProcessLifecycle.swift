public enum LifecycleEffect: Equatable, Sendable {
    case start
    case terminate(String)
    case scheduleDrainDeadline(String)
    case drainTimedOut(String)
    case quit
}

public enum ChildStream: Hashable, Sendable { case stdout, stderr }

public struct ProcessLifecycle {
    public private(set) var session: String?
    public private(set) var isSleeping = false
    public private(set) var isQuitting = false
    public private(set) var stopRequested = false
    private var restartWhenExited = false
    private var processExited = false
    private var drainDeadlineScheduled = false
    private var openStreams: Set<ChildStream> = [.stdout, .stderr]

    public init() {}

    public mutating func didStart(_ session: String) {
        self.session = session
        stopRequested = false
        processExited = false
        drainDeadlineScheduled = false
        openStreams = [.stdout, .stderr]
    }

    public func canInteract(with session: String) -> Bool {
        self.session == session && !processExited && !stopRequested && !isSleeping && !isQuitting
    }

    public mutating func requestStart() -> [LifecycleEffect] {
        guard session == nil && !isSleeping && !isQuitting else { return [] }
        return [.start]
    }

    public mutating func requestStop() -> [LifecycleEffect] {
        guard let session, !stopRequested, !processExited else { return [] }
        stopRequested = true
        return [.terminate(session)]
    }

    public mutating func requestSleep() -> [LifecycleEffect] {
        isSleeping = true
        restartWhenExited = false
        return requestStop()
    }

    public mutating func requestWake() -> [LifecycleEffect] {
        guard !isQuitting else { return [] }
        isSleeping = false
        if session != nil {
            restartWhenExited = stopRequested
            return []
        }
        return [.start]
    }

    public mutating func requestQuit() -> [LifecycleEffect] {
        isQuitting = true
        restartWhenExited = false
        return session == nil ? [.quit] : requestStop()
    }

    public mutating func didExit(_ session: String) -> [LifecycleEffect] {
        guard self.session == session else { return [] }
        processExited = true
        if !openStreams.isEmpty && !drainDeadlineScheduled {
            drainDeadlineScheduled = true
            return [.scheduleDrainDeadline(session)]
        }
        return retireIfDrained()
    }

    public mutating func drainDeadlineExpired(_ session: String) -> [LifecycleEffect] {
        guard self.session == session && processExited && !openStreams.isEmpty else { return [] }
        openStreams.removeAll()
        return [.drainTimedOut(session)] + retireIfDrained()
    }

    public mutating func didClose(_ stream: ChildStream, session: String) -> [LifecycleEffect] {
        guard self.session == session else { return [] }
        openStreams.remove(stream)
        return retireIfDrained()
    }

    private mutating func retireIfDrained() -> [LifecycleEffect] {
        guard processExited && openStreams.isEmpty else { return [] }
        self.session = nil
        stopRequested = false
        if isQuitting { return [.quit] }
        if restartWhenExited && !isSleeping {
            restartWhenExited = false
            return [.start]
        }
        return []
    }
}
