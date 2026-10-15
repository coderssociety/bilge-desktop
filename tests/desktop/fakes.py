from bilge.desktop.process import Completed, MissingProgram


class FakeRunner:
    """Records the programs run and answers from a script keyed by the first words of the command."""

    def __init__(self, installed=(), answers=None):
        self.installed = set(installed)
        self.answers = answers or {}
        self.calls = []
        self.spawned = []
        self.fed = []

    def which(self, program):
        return f"/usr/bin/{program}" if program in self.installed else None

    def has(self, program):
        return program in self.installed

    def _answer(self, argv):
        for size in range(len(argv), 0, -1):
            key = " ".join(argv[:size])
            if key in self.answers:
                answer = self.answers[key]
                return answer if isinstance(answer, Completed) else Completed(0, answer, "")
        return Completed(0, "", "")

    def run(self, argv, input=None, timeout=15, capture=True):
        if argv[0] not in self.installed:
            raise MissingProgram(argv[0])
        self.calls.append((list(argv), input))
        return self._answer(argv)

    def check(self, argv, input=None, timeout=15):
        done = self.run(argv, input=input, timeout=timeout)
        if not done.ok:
            from bilge.desktop.process import DesktopError

            raise DesktopError(done.stderr)
        return done.stdout

    def spawn(self, argv):
        if argv[0] not in self.installed:
            raise MissingProgram(argv[0])
        self.spawned.append(list(argv))

    def feed(self, argv, source, timeout=15):
        self.fed.append((list(argv), source))

    @property
    def commands(self):
        return [argv for argv, _ in self.calls]
