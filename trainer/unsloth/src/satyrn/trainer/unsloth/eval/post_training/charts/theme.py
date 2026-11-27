"""Dark theme with Satyrn logo for charts."""

from pathlib import Path

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.image import imread

BACKGROUND = "#101114"
BAND_TINTS = ("#14161a", "#191b21")
TEXT = "#c9ccd1"
MUTED = "#8a8e97"
GRID = "#23252b"
LOSS_GRAY = "#6b6f78"
PALETTE = ("#E69F00", "#56B4E9", "#009E73", "#F0E442")


def style_axes(*axes: Axes) -> None:
    """Make the axes transparent, with light tick labels and no frame."""
    for axis in axes:
        axis.set_facecolor("none")
        axis.tick_params(colors=TEXT, pad=8)
        for spine in axis.spines.values():
            spine.set_visible(False)


def add_logo(figure: Figure) -> None:
    """Place the Satyrn logo in the bottom right corner of the figure."""
    logo = imread(Path(__file__).with_name("satyrn-graphic-dark.png"))
    rows, columns = np.where(logo[..., 3] > 0)
    logo = logo[rows.min() : rows.max() + 1, columns.min() : columns.max() + 1]

    width = 0.045
    height = width * logo.shape[0] / logo.shape[1] * figure.get_figwidth() / figure.get_figheight()
    logo_axis = figure.add_axes([0.91 - width, 0.09, width, height])
    logo_axis.imshow(logo)
    logo_axis.axis("off")
