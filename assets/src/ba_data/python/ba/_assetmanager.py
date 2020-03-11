# Copyright (c) 2011-2020 Eric Froemling
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# -----------------------------------------------------------------------------
"""Functionality related to managing cloud based assets."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path
import urllib.request
import logging
import weakref
import time
import os
import sys
# import atexit

from efro import entity

if TYPE_CHECKING:
    from bacommon.assets import AssetPackageFlavor
    from typing import List


class FileValue(entity.CompoundValue):
    """State for an individual file."""


class State(entity.Entity):
    """Holds all persistent state for the asset-manager."""

    files = entity.CompoundDictField('files', str, FileValue())


class AssetManager:
    """Wrangles all assets."""

    _state: State

    def __init__(self, rootdir: Path) -> None:
        print('AssetManager()')
        assert isinstance(rootdir, Path)
        self._rootdir = rootdir
        self._shutting_down = False
        if not self._rootdir.is_dir():
            raise RuntimeError(f'Provided rootdir does not exist: "{rootdir}"')

        self.load_state()

        # atexit.register(self._at_exit)

    def __del__(self) -> None:
        self._shutting_down = True
        self.update()
        print('~AssetManager()')

    # @staticmethod
    # def _at_exit() -> None:
    #     print('HELLO FROM SHUTDOWN')

    def launch_gather(
            self,
            packages: List[str],
            flavor: AssetPackageFlavor,
            account_token: str,
    ) -> AssetGather:
        """Spawn an asset-gather operation from this manager."""
        print('would gather', packages, 'and flavor', flavor, 'with token',
              account_token)
        return AssetGather(self)

    def update(self) -> None:
        """Can be called periodically to perform upkeep."""

        # Currently we always write state when shutting down.
        if self._shutting_down:
            self.save_state()

    @property
    def rootdir(self) -> Path:
        """The root directory for this manager."""
        return self._rootdir

    @property
    def state_path(self) -> Path:
        """The path of the state file."""
        return Path(self._rootdir, 'state')

    def load_state(self) -> None:
        """Loads state from disk. Resets to default state if unable to."""
        print('AMAN LOADING STATE')
        try:
            state_path = self.state_path
            if state_path.exists():
                with open(self.state_path) as infile:
                    self._state = State.from_json_str(infile.read())
                    return
        except Exception:
            logging.exception('Error loading existing AssetManager state')
        self._state = State()

    def save_state(self) -> None:
        """Save state to disk (if possible)."""
        print('AMAN SAVING STATE')
        try:
            with open(self.state_path, 'w') as outfile:
                outfile.write(self._state.to_json_str())
        except Exception:
            logging.exception('Error writing AssetManager state')


class AssetGather:
    """Wrangles a gather of assets."""

    def __init__(self, manager: AssetManager) -> None:
        self._manager = weakref.ref(manager)
        self._valid = True
        print('AssetGather()')
        fetch_url("http://www.python.org/ftp/python/2.7.3/Python-2.7.3.tgz",
                  filename=Path(manager.rootdir, 'testdl'),
                  asset_gather=self)
        print('fetch success')

    @property
    def valid(self) -> bool:
        """Whether this gather is still valid.

        A gather becomes in valid if its originating AssetManager dies.
        """
        return True

    def __del__(self) -> None:
        print('~AssetGather()')


def fetch_url(url: str, filename: Path, asset_gather: AssetGather) -> None:
    """Fetch a given url to a given filename for a given AssetGather.

    This """

    import socket

    # We don't want to keep the provided AssetGather alive, but we want
    # to abort if it dies.
    assert isinstance(asset_gather, AssetGather)
    weak_gather = weakref.ref(asset_gather)

    # Pass a very short timeout to urllib so we have opportunities
    # to cancel even with network blockage.
    ureq = urllib.request.urlopen(url, None, 1)
    file_size = int(ureq.headers["Content-Length"])
    print(f"\nDownloading: {filename} Bytes: {file_size:,}")

    with open(filename, 'wb') as outfile:
        file_size_dl = 0

        # I'm guessing we want this decently big so we're running fewer cycles
        # of this loop during downloads and keeping our load lower. Our timeout
        # should ensure a minimum rate for the loop and this will affect
        # the maximum. Perhaps we should aim for a few cycles per second on
        # an average connection?..
        block_sz = 1024 * 100 * 2
        time_outs = 0
        while True:
            try:
                data = ureq.read(block_sz)
            except socket.timeout:

                # File has not had activity in max seconds.
                if time_outs > 3:
                    print("\n\n\nsorry -- try back later")
                    os.unlink(filename)
                    raise
                print("\nHmmm... little issue... "
                      "I'll wait a couple of seconds")
                time.sleep(3)
                time_outs += 1
                continue

            # We reached the end of the download!
            if not data:
                sys.stdout.write('\rDone!\n\n')
                sys.stdout.flush()
                break

            file_size_dl += len(data)
            outfile.write(data)
            percent = file_size_dl * 1.0 / file_size
            status = f'{file_size_dl:20,} Bytes [{percent:.2%}] received'
            sys.stdout.write('\r' + status)
            sys.stdout.flush()
