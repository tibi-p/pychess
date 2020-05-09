import os

from pychess.compat import create_task
from pychess.System.prefix import addDataPrefix
from pychess.Utils.const import WHITE, BLACK, LOCAL, NORMALCHESS, ARTIFICIAL, \
    WAITING_TO_START, HINT, PRACTICE_GOAL_REACHED, CUSTOM_PUZZLE
from pychess.Utils.LearnModel import LearnModel
from pychess.Utils.TimeModel import TimeModel
from pychess.Variants import variants
from pychess.Players.Human import Human
from pychess.Players.engineNest import discoverer
from pychess.perspectives import perspective_manager
from pychess.perspectives.learn.generate.generateLessonsSidepanel import generateLessonsSidepanel
from pychess.perspectives.learn import lessons_solving_progress
from pychess.perspectives.learn import custom_puzzles_solving_progress
from pychess.Savers.olv import OLVFile
from pychess.Savers.pgn import PGNFile
from pychess.System import conf
from pychess.System.protoopen import protoopen

__title__ = _("Custom Puzzles")

__icon__ = addDataPrefix("glade/panel_book.svg")

__desc__ = _("Custom Puzzles for Chess")


puzzles0 = []
for elem in sorted(os.listdir(path=addDataPrefix("learn/custom_puzzles/"))):
    if elem.endswith(".pgn"):
        puzzles0.append((elem, elem.split(".pgn")[0].capitalize(), _("others")))

CUSTOM_PUZZLES = puzzles0

# Note: Find the declaration of the class Sidepanel at the end of the file


def start_custom_puzzle_from(filename, index=None):
    if filename.lower().endswith(".pgn"):
        chessfile = PGNFile(protoopen(addDataPrefix("learn/custom_puzzles/%s" % filename)))
        chessfile.limit = 1000
        chessfile.init_tag_database()
    elif filename.lower().endswith(".olv"):
        chessfile = OLVFile(protoopen(addDataPrefix("learn/custom_puzzles/%s" % filename), encoding="utf-8"))

    records, plys = chessfile.get_records()

    progress = custom_puzzles_solving_progress.get(filename, [0] * chessfile.count)

    if index is None:
        try:
            index = progress.index(0)
        except ValueError:
            index = 0

    rec = records[index]

    timemodel = TimeModel(0, 0)
    gamemodel = LearnModel(timemodel)

    chessfile.loadToModel(rec, 0, gamemodel)

    start_custom_puzzle_game(gamemodel, filename, records, index, rec)


def start_custom_puzzle_game(gamemodel, filename, records, index, rec, from_lesson=False):
    gamemodel.set_learn_data(CUSTOM_PUZZLE, filename, index, len(records), from_lesson=from_lesson)

    engine = discoverer.getEngineByName(discoverer.getEngineLearn())
    ponder_off = True

    color = gamemodel.boards[gamemodel.start_ply_num].color

    w_name = "" if rec["White"] is None else rec["White"]
    b_name = "" if rec["Black"] is None else rec["Black"]

    player_name = conf.get("firstName")
    engine_name = discoverer.getName(engine)

    if rec["Event"].startswith("Lichess Practice"):
        w_name = player_name if color == WHITE else engine_name
        b_name = engine_name if color == WHITE else player_name

    opp_name = b_name if color == WHITE else w_name

    if color == WHITE:
        p0 = (LOCAL, Human, (WHITE, w_name), w_name)
        p1 = (ARTIFICIAL, discoverer.initPlayerEngine,
              (engine, BLACK, 20, variants[NORMALCHESS], 20, 0, 0, ponder_off), b_name)
    else:
        p0 = (ARTIFICIAL, discoverer.initPlayerEngine,
              (engine, WHITE, 20, variants[NORMALCHESS], 20, 0, 0, ponder_off), w_name)
        p1 = (LOCAL, Human, (BLACK, b_name), b_name)

    def on_game_started(gamemodel, name, color):
        perspective.activate_panel("annotationPanel")
        create_task(gamemodel.start_analyzer(HINT, force_engine=discoverer.getEngineLearn()))
        gamemodel.players[1 - color].name = name
        gamemodel.emit("players_changed")
    gamemodel.connect("game_started", on_game_started, opp_name, color)

    def goal_checked(gamemodle):
        if gamemodel.reason == PRACTICE_GOAL_REACHED:
            if from_lesson:
                progress = lessons_solving_progress[gamemodel.source]
            else:
                progress = custom_puzzles_solving_progress[gamemodel.source]

            progress[gamemodel.current_index] = 1

            if from_lesson:
                lessons_solving_progress[gamemodel.source] = progress
            else:
                custom_puzzles_solving_progress[gamemodel.source] = progress
    gamemodel.connect("goal_checked", goal_checked)

    gamemodel.variant.need_initial_board = True
    gamemodel.status = WAITING_TO_START

    perspective = perspective_manager.get_perspective("games")
    create_task(perspective.generalStart(gamemodel, p0, p1))


# Sidepanel is a class
Sidepanel = generateLessonsSidepanel(
    solving_progress=custom_puzzles_solving_progress,
    learn_category_id=CUSTOM_PUZZLE,
    entries=CUSTOM_PUZZLES,
    start_from=start_custom_puzzle_from,
)
