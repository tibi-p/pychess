import asyncio

from gi.repository import GObject

from pychess.Utils.const import BLACKWON, WHITEWON, DRAW, UNDOABLE_STATES,\
    CANCELLED, PRACTICE_GOAL_REACHED, BLACK, WHITE, LECTURE, LESSON, PUZZLE, ENDGAME, CUSTOM_PUZZLE
from pychess.Utils.GameModel import GameModel

learn2str = {
    LECTURE: "Lecture",
    PUZZLE: "Puzzle",
    LESSON: "Lesson",
    ENDGAME: "Endgame",
    CUSTOM_PUZZLE: "Custom Puzzle",
}

MATE, MATE_IN, DRAW_IN, EQUAL_IN, EVAL_IN, PROMOTION, ONE_MOVE = range(7)


class Goal():
    def __init__(self, termination):
        self.termination = termination
        # print(termination)

        if termination.startswith("mate in"):
            self.result = MATE_IN
            self.moves = int(termination.split()[-1])
            self.cp = None
        elif termination.startswith("draw in"):
            self.result = DRAW_IN
            self.moves = int(termination.split()[-1])
            self.cp = None
        elif termination.startswith("equalize in"):
            self.result = EQUAL_IN
            self.moves = int(termination.split()[-1])
            self.cp = None
        elif termination.startswith("in n moves"):
            self.result = ONE_MOVE
            parts = termination.split()
            self.moves = int(parts[-1][2:])
            self.cp = None
        elif "cp in" in termination:
            self.result = EVAL_IN
            parts = termination.split()
            self.moves = int(parts[-1])
            self.cp = int(parts[0][1:-2])
        elif "promotion with" in termination:
            self.result = PROMOTION
            self.moves = None
            parts = termination.split()
            self.cp = int(parts[-1][1:-2])
        else:
            self.result = MATE
            self.moves = None
            self.cp = None
            # print("No termination tag, expecting MATE", termination)


class LearnModel(GameModel):
    __gsignals__ = {
        # goal_checked is emitted after puzzle game goal check finished
        "goal_checked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "learn_success": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def isChanged(self):
        """ Never save learn games changes to .pgn """
        return False

    def set_learn_data(self, learn_type, source, current_index=None, game_count=None, from_lesson=False):
        self.learn_type = learn_type
        self.source = source
        self.current_index = current_index
        self.game_count = game_count
        self.from_lesson = from_lesson

        self.hints = {}
        self.goal = None
        self.failed_playing_best = False
        self.score_delta = None

        if learn_type == LECTURE:
            self.offline_lecture = True
            self.lecture_skip_event = asyncio.Event()  # set when 'Go on' button pressed
            self.lecture_pause_event = asyncio.Event()  # set when 'Pause' button pressed
            self.lecture_exit_event = asyncio.Event()  # set when 'Exit' button pressed

        elif learn_type == PUZZLE:
            self.puzzle_game = True
            self.goal = Goal(self.tags["Termination"])

        elif learn_type == LESSON:
            self.lesson_game = True

        elif learn_type == ENDGAME:
            self.end_game = True

        elif learn_type == CUSTOM_PUZZLE:
            self.puzzle_game = True
            num_moves = 1
            self.goal = Goal("in n moves n={}".format(num_moves))

    def parse_eval_hints(self):
        if not self.hints and self.full_eval:
            for k, v in self.full_eval.items():
                real_ply = self.lowply + k
                if real_ply >= self.ply:
                    self.hints[real_ply] = self.full_eval[k][1]

    def check_failed_playing_best(self, status):
        player_move = self.moves[-1].as_uci()
        if self.ply - 1 in self.hints:
            ply_eval = self.hints[self.ply - 1]
            best_score = ply_eval[0][1]
            best_moves = [hint[0] for hint in ply_eval if abs(hint[1] - best_score) <= 10]
            player_score = next(x[1] for x in ply_eval if x[0] == player_move)
            if player_score is not None:
                self.score_delta = (best_score, player_score)
        else:
            best_moves = []

        if self.puzzle_game:
            # No need to check in best moves (and let add more time to analyzer) in trivial cases
            if self.goal.result in (MATE, MATE_IN) and (
                (status == BLACKWON and self.starting_color == BLACK) or
                    (status == WHITEWON and self.starting_color == WHITE)):
                return False
            elif self.goal.result == DRAW_IN and status == DRAW:
                return False
            elif self.goal.result in (MATE_IN, DRAW_IN, EQUAL_IN, EVAL_IN, PROMOTION, ONE_MOVE):
                expect_best = self.goal.result != ONE_MOVE
            else:
                expect_best = False
        else:
            expect_best = False

        failed = expect_best and player_move not in best_moves
        return failed

    def check_goal(self, status, reason):
        if self.end_game:
            if status in UNDOABLE_STATES:
                self.end(status, reason)
            self.emit("goal_checked")
            return

        full_moves = (self.ply - self.start_ply) // 2 + 1
        # print("Is Goal not reached?", self.goal.result, status, full_moves, self.goal.moves, self.failed_playing_best)

        if (self.goal.result == DRAW_IN and status == DRAW and full_moves <= self.goal.moves) or \
           (self.goal.result == MATE_IN and status == WHITEWON and full_moves <= self.goal.moves and self.starting_color == WHITE) or \
           (self.goal.result == MATE_IN and status == BLACKWON and full_moves <= self.goal.moves and self.starting_color == BLACK) or \
           (self.goal.result in (EVAL_IN, EQUAL_IN) and full_moves == self.goal.moves and not self.failed_playing_best) or \
           (self.goal.result == ONE_MOVE and full_moves == self.goal.moves and not self.failed_playing_best) or \
           (self.goal.result == MATE and status in (WHITEWON, BLACKWON)) or \
           (self.goal.result == PROMOTION and self.moves[-1].promotion):
            if status in UNDOABLE_STATES:
                self.end(status, PRACTICE_GOAL_REACHED)
            else:
                self.end(CANCELLED, PRACTICE_GOAL_REACHED)
        else:
            if status in UNDOABLE_STATES:
                # print("check_goal() status in UNDOABLE_STATES -> self.end(status, reason)")
                self.failed_playing_best = True
                self.end(status, reason)
            # print("Goal not reached yet.", self.goal.result, status, full_moves, self.goal.moves, self.failed_playing_best)

        self.emit("goal_checked")
        return
