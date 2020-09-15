#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import abc
import logging
import sys
from pathlib import Path
from typing import Any, cast, Dict, Final, Generic, Optional, TypeVar, Union

import cmk.utils
import cmk.utils.debug
import cmk.utils.log  # TODO: Remove this!
import cmk.utils.misc
import cmk.utils.paths
import cmk.utils.tty as tty
from cmk.utils.exceptions import MKSNMPError, MKTimeout, MKIPAddressLookupError
from cmk.utils.log import VERBOSE
from cmk.utils.type_defs import (
    HostAddress,
    HostName,
    Result,
    SectionName,
    ServiceCheckResult,
    SourceType,
)

from cmk.snmplib.type_defs import TRawData

from cmk.fetchers import ABCFetcher
from cmk.fetchers.controller import FetcherType
from cmk.fetchers.type_defs import Mode

import cmk.base.check_api_utils as check_api_utils
import cmk.base.config as config
import cmk.base.cpu_tracking as cpu_tracking
from cmk.base.check_utils import (
    PiggybackRawData,
    SectionCacheInfo,
    TPersistedSections,
    TSectionContent,
    TSections,
)
from cmk.base.config import HostConfig, SelectedRawSections
from cmk.base.exceptions import MKAgentError, MKEmptyAgentData

from ._cache import SectionStore

__all__ = [
    "ABCHostSections",
    "ABCSource",
    "ABCChecker",
    "FileCacheConfigurer",
    "Mode",
    "set_cache_opts",
]


class ABCHostSections(Generic[TRawData, TSections, TPersistedSections, TSectionContent],
                      metaclass=abc.ABCMeta):
    """A wrapper class for the host information read by the data sources

    It contains the following information:

        1. sections:                A dictionary from section_name to a list of rows,
                                    the section content
        2. piggybacked_raw_data:    piggy-backed data for other hosts
        3. persisted_sections:      Sections to be persisted for later usage
        4. cache_info:              Agent cache information
                                    (dict section name -> (cached_at, cache_interval))
    """
    def __init__(
        self,
        sections: Optional[TSections] = None,
        cache_info: Optional[SectionCacheInfo] = None,
        piggybacked_raw_data: Optional[PiggybackRawData] = None,
        persisted_sections: Optional[TPersistedSections] = None,
    ) -> None:
        super().__init__()
        self.sections = sections if sections else {}
        self.cache_info = cache_info if cache_info else {}
        self.piggybacked_raw_data = piggybacked_raw_data if piggybacked_raw_data else {}
        self.persisted_sections = persisted_sections if persisted_sections else {}

    def __repr__(self):
        return "%s(sections=%r, cache_info=%r, piggybacked_raw_data=%r, persisted_sections=%r)" % (
            type(self).__name__,
            self.sections,
            self.cache_info,
            self.piggybacked_raw_data,
            self.persisted_sections,
        )

    # TODO: It should be supported that different sources produce equal sections.
    # this is handled for the self.sections data by simply concatenating the lines
    # of the sections, but for the self.cache_info this is not done. Why?
    # TODO: checking.execute_check() is using the oldest cached_at and the largest interval.
    #       Would this be correct here?
    def update(self, host_sections: "ABCHostSections") -> None:
        """Update this host info object with the contents of another one"""
        for section_name, section_content in host_sections.sections.items():
            self._extend_section(section_name, section_content)

        for hostname, raw_lines in host_sections.piggybacked_raw_data.items():
            self.piggybacked_raw_data.setdefault(hostname, []).extend(raw_lines)

        if host_sections.cache_info:
            self.cache_info.update(host_sections.cache_info)

        if host_sections.persisted_sections:
            self.persisted_sections.update(host_sections.persisted_sections)

    def add_persisted_sections(
        self,
        persisted_sections_file_path: Path,
        use_outdated_persisted_sections: bool,
        *,
        logger: logging.Logger,
    ):
        """Add information from previous persisted infos."""
        persisted_sections = self._determine_persisted_sections(
            persisted_sections_file_path,
            use_outdated_persisted_sections,
            logger=logger,
        )
        self._add_persisted_sections(
            persisted_sections,
            logger=logger,
        )

    def _determine_persisted_sections(
        self,
        persisted_sections_file_path: Path,
        use_outdated_persisted_sections: bool,
        *,
        logger: logging.Logger,
    ) -> TPersistedSections:
        # TODO(ml): This function should take a TPersistedSections
        #           instead of the host_section but mypy does not allow it.
        section_store: SectionStore[TPersistedSections] = SectionStore(
            persisted_sections_file_path,
            logger,
        )
        persisted_sections = section_store.load(use_outdated_persisted_sections)
        if persisted_sections != self.persisted_sections:
            persisted_sections.update(self.persisted_sections)
            section_store.store(persisted_sections)
        return persisted_sections

    def _add_persisted_sections(
        self,
        persisted_sections: TPersistedSections,
        *,
        logger: logging.Logger,
    ) -> None:
        if not persisted_sections:
            return

        for section_name, entry in persisted_sections.items():
            if len(entry) == 2:
                continue  # Skip entries of "old" format

            # Don't overwrite sections that have been received from the source with this call
            if section_name in self.sections:
                logger.debug("Skipping persisted section %r, live data available", section_name)
                continue

            logger.debug("Using persisted section %r", section_name)
            self._add_cached_section(section_name, *entry)

    def _extend_section(
        self,
        section_name: SectionName,
        section_content: TSectionContent,
    ) -> None:
        self.sections.setdefault(section_name, []).extend(section_content)

    def _add_cached_section(
        self,
        section_name: SectionName,
        persisted_from: int,
        persisted_until: int,
        section: TSectionContent,
    ) -> None:
        self.cache_info[section_name] = (persisted_from, persisted_until - persisted_from)
        # TODO: Find out why mypy complains about this
        self.sections[section_name] = section  # type: ignore[assignment]


THostSections = TypeVar("THostSections", bound=ABCHostSections)


class ABCParser(Generic[TRawData, THostSections], metaclass=abc.ABCMeta):
    """Parse raw data into host sections.

    Note:
        Only private methods are allowed to handle `TRawData` and
        `THostSections`.  Public methods must always use
        `Result[TRawData, Exception]` and `Result[THostSections, Exception]`.

    """
    def __init__(self, hostname: HostName, logger: logging.Logger) -> None:
        super().__init__()
        self.hostname: Final[HostName] = hostname
        self.host_config = config.HostConfig.make_host_config(self.hostname)
        self._logger = logger

    def parse(
        self,
        raw_data: Result[TRawData, Exception],
    ) -> Result[THostSections, Exception]:
        if raw_data.is_err():
            return Result.Err(raw_data.unwrap_err())
        try:
            assert raw_data.ok is not None
            return Result.OK(self._parse(raw_data.ok))
        except Exception as exc:
            return Result.Err(exc)

    @abc.abstractmethod
    def _parse(self, raw_data: TRawData) -> THostSections:
        raise NotImplementedError


def set_cache_opts(use_caches: bool) -> None:
    # TODO check these settings vs.
    # cmk/base/automations/check_mk.py:_set_cache_opts_of_checkers
    if use_caches:
        FileCacheConfigurer.maybe = True
        FileCacheConfigurer.use_outdated = True


class FileCacheConfigurer:
    """Hold the configuration to FileCache."""

    # TODO: Clean these options up! We need to change all call sites to use
    #       a single Checkers() object during processing first. Then we
    #       can change these class attributes to object attributes.
    #
    # Set by the user via command line to prevent using cached information at all.
    # Is also set by inventory for SNMP checks to handle the special situation that
    # the inventory is not allowed to use the regular checking based SNMP data source
    # cache.
    disabled: bool = False
    snmp_disabled: bool = False
    agent_disabled: bool = False
    # Set by the code in different situations where we recommend, but not enforce,
    # to use the cache. The user can always use "--cache" to override this.
    # It's used to 'transport' caching opt between modules, eg:
    # - modes: FileCacheConfigurer.maybe = use_caches
    # - discovery: use_caches = FileCacheConfigurer.maybe
    maybe = False
    # Is set by the "--cache" command line. This makes the caching logic use
    # cache files that are even older than the max_cachefile_age of the host/mode.
    use_outdated = False

    def __init__(
        self,
        path: Union[Path, str],
        fetcher_type: FetcherType,
        *,
        max_age: Optional[int] = None,
        simulation: bool = False,
    ):
        super().__init__()
        self.path = Path(path)
        self.fetcher_type: FetcherType = fetcher_type
        self.max_age: Optional[int] = max_age
        self.simulation: bool = simulation

    @classmethod
    def reset_maybe(cls):
        cls.maybe = not cls.disabled

    def configure(self) -> Dict[str, Any]:
        disabled = self.disabled
        if self.fetcher_type is FetcherType.SNMP:
            disabled |= self.snmp_disabled
        else:
            disabled |= self.agent_disabled
        return {
            "path": str(self.path),
            "max_age": self.max_age,
            "disabled": disabled,
            "use_outdated": self.use_outdated,
            "simulation": self.simulation,
        }


class ABCSource(Generic[TRawData, THostSections], metaclass=abc.ABCMeta):
    """Hold the configuration to fetchers and checkers.

    At best, this should only hold static data, that is, every
    attribute is final.

    Dump the JSON configuration from `configure_fetcher()`.

    """
    def __init__(
        self,
        hostname: HostName,
        ipaddress: Optional[HostAddress],
        *,
        mode: Mode,
        source_type: SourceType,
        fetcher_type: FetcherType,
        description: str,
        default_raw_data: TRawData,
        default_host_sections: THostSections,
        id_: str,
        cpu_tracking_id: str,
        cache_dir: Optional[Path] = None,
        persisted_section_dir: Optional[Path] = None,
    ) -> None:
        self.hostname: Final[str] = hostname
        self.ipaddress: Final[Optional[str]] = ipaddress
        self.mode: Final[Mode] = mode
        self.source_type: Final[SourceType] = source_type
        self.fetcher_type: Final[FetcherType] = fetcher_type
        self.description: Final[str] = description
        self.default_raw_data: Final = default_raw_data
        self.default_host_sections: Final[THostSections] = default_host_sections
        self.id: Final[str] = id_
        self.cpu_tracking_id: Final[str] = cpu_tracking_id
        if not cache_dir:
            cache_dir = Path(cmk.utils.paths.data_source_cache_dir) / self.id
        if not persisted_section_dir:
            persisted_section_dir = Path(cmk.utils.paths.var_dir) / "persisted_sections" / self.id

        self.file_cache = FileCacheConfigurer(
            cache_dir / self.hostname,
            self.fetcher_type,
            simulation=config.simulation_mode,
        )
        self.persisted_sections_file_path: Final[Path] = persisted_section_dir / self.hostname
        self.selected_raw_sections: Optional[SelectedRawSections] = None

        self.host_config: Final[HostConfig] = HostConfig.make_host_config(hostname)
        self._logger: Final[logging.Logger] = logging.getLogger("cmk.base.data_source.%s" % id_)

        self.exit_spec = self.host_config.exit_code_spec(id_)

    def __repr__(self) -> str:
        return "%s(%r, %r, mode=%r, description=%r, id=%r)" % (
            type(self).__name__,
            self.hostname,
            self.ipaddress,
            self.mode,
            self.description,
            self.id,
        )

    def fetch(self) -> Result[TRawData, Exception]:
        try:
            with self._make_fetcher() as fetcher:
                return Result.OK(fetcher.fetch(self.mode))
        except Exception as exc:
            return Result.Err(exc)

    def parse(self, raw_data: Result[TRawData, Exception]) -> Result[THostSections, Exception]:
        # That should obviously call `make_parser().parse(...)` but we still have
        # cruft in `Checker.check()` that we cannot yet easily get rid of.
        return self._make_checker().check(raw_data)

    def summarize(self, host_sections: Result[THostSections, Exception]) -> ServiceCheckResult:
        return self._make_summarizer().summarize(host_sections)

    @abc.abstractmethod
    def configure_fetcher(self) -> Dict[str, Any]:
        """Return a fetcher configuration suitable to create a fetcher.

        See Also:
            FetcherType: A fetcher factory.

        """
        raise NotImplementedError

    def _make_fetcher(self) -> ABCFetcher:
        """Create a fetcher with this configuration."""
        return self.fetcher_type.from_json(self.configure_fetcher())

    @abc.abstractmethod
    def _make_checker(self) -> "ABCChecker":
        """Create a checker with this configuration."""
        raise NotImplementedError

    @abc.abstractmethod
    def _make_parser(self) -> "ABCParser[TRawData, THostSections]":
        """Create a parser with this configuration."""
        raise NotImplementedError

    @abc.abstractmethod
    def _make_summarizer(self) -> "ABCSummarizer[THostSections]":
        """Create a summarizer with this configuration."""
        raise NotImplementedError

    def _setup_logger(self) -> None:
        """Add the source log prefix to the class logger"""
        self._logger.propagate = False
        handler = logging.StreamHandler(stream=sys.stdout)
        fmt = " %s[%s%s%s]%s %%(message)s" % (tty.bold, tty.normal, self.id, tty.bold, tty.normal)
        handler.setFormatter(logging.Formatter(fmt))
        del self._logger.handlers[:]  # Remove all previously existing handlers
        self._logger.addHandler(handler)


class ABCSummarizer(Generic[THostSections], metaclass=abc.ABCMeta):
    """Class to summarize parsed data into a ServiceCheckResult.

    Note:
        Only private methods are allowed to handle `THostSections`.
        Public methods must always use `Result[THostSections, Exception]`.

    """
    def __init__(self, exit_spec: config.ExitSpec) -> None:
        super().__init__()
        self.exit_spec: Final[config.ExitSpec] = exit_spec

    def summarize(
        self,
        host_sections: Result[THostSections, Exception],
    ) -> ServiceCheckResult:
        """Summarize the host sections."""
        if host_sections.is_ok():
            assert host_sections.ok is not None
            return self._summarize(host_sections.ok)

        assert host_sections.err is not None
        exc_msg = "%s" % host_sections.err
        status = self._extract_status(host_sections.err)
        return status, exc_msg + check_api_utils.state_markers[status], []

    def _extract_status(self, exc: Exception) -> int:
        if isinstance(exc, MKEmptyAgentData):
            status = self.exit_spec.get("empty_output", 2)
        elif isinstance(exc, (MKAgentError, MKIPAddressLookupError, MKSNMPError)):
            status = self.exit_spec.get("connection", 2)
        elif isinstance(exc, MKTimeout):
            status = self.exit_spec.get("timeout", 2)
        else:
            status = self.exit_spec.get("exception", 3)
        return cast(int, status)

    @abc.abstractmethod
    def _summarize(self, host_sections: THostSections) -> ServiceCheckResult:
        raise NotImplementedError


class ABCChecker(Generic[TRawData, TSections, TPersistedSections, THostSections],
                 metaclass=abc.ABCMeta):
    """Parse raw data into host sections."""
    _use_outdated_persisted_sections = False

    def __init__(
        self,
        source: ABCSource,
        persisted_sections_file_path: Path,
    ) -> None:
        super().__init__()
        self.source = source
        self._persisted_sections_file_path = persisted_sections_file_path
        self._logger = self.source._logger

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.source)

    @property
    def id(self) -> str:
        return self.source.id

    @property
    def _cpu_tracking_id(self) -> str:
        return self.source.cpu_tracking_id

    @cpu_tracking.track
    def check(self, raw_data: Result[TRawData, Exception]) -> Result[THostSections, Exception]:
        # WARNING: Do not call this function.  It is meant to disappear.
        try:
            host_sections = self.source._make_parser().parse(raw_data)
            if host_sections.is_err():
                return host_sections

            assert host_sections.ok is not None
            host_sections.ok.add_persisted_sections(
                self._persisted_sections_file_path,
                self.use_outdated_persisted_sections,
                logger=self._logger,
            )
            return host_sections
        except Exception as exc:
            self._logger.log(VERBOSE, "ERROR: %s", exc)
            if cmk.utils.debug.enabled():
                raise
            return Result.Err(exc)

    @classmethod
    def use_outdated_persisted_sections(cls) -> None:
        cls._use_outdated_persisted_sections = True
