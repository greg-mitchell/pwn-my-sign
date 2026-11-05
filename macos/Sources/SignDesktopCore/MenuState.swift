public struct MenuState {
    public private(set) var view: WorkflowView?
    public private(set) var awaitingView = false
    private var pendingNotifications: Set<String> = []

    public init() {}

    public mutating func beginNotification(_ id: String) {
        pendingNotifications.insert(id)
    }

    public mutating func finishNotification(_ id: String) {
        pendingNotifications.remove(id)
    }

    @discardableResult
    public mutating func receive(_ next: WorkflowView) -> Bool {
        guard next.revision > (view?.revision ?? -1) else { return false }
        view = next
        awaitingView = false
        return true
    }

    public var canUpload: Bool {
        pendingNotifications.isEmpty && !awaitingView
            && view?.uploadAvailable == true && view?.phase.isBusy == false
    }

    public var canCheck: Bool {
        pendingNotifications.isEmpty && !awaitingView && view != nil && view?.phase.isBusy == false
    }

    public mutating func take(_ action: MenuAction) -> ActionRecord? {
        guard (action == .upload ? canUpload : canCheck), let view else { return nil }
        awaitingView = true
        return ActionRecord(action: action, revision: view.revision)
    }
}
