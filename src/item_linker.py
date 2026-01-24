"""Item linking algorithm with fuzzy matching for duplicate name handling"""

import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass
from difflib import SequenceMatcher

from state_manager_v2 import StateManagerV2, PaprikaItem, SkylightItem

logger = logging.getLogger(__name__)


@dataclass
class ItemMatch:
    """Represents a potential match between Paprika and Skylight items"""
    paprika_item: PaprikaItem
    skylight_item: SkylightItem
    confidence_score: float
    match_reason: str


class ItemLinker:
    """
    Links Paprika and Skylight items intelligently, handling duplicate names
    and fuzzy matching scenarios
    """

    def __init__(self, state_manager: StateManagerV2, config: dict = None):
        """
        Initialize ItemLinker

        Args:
            state_manager: StateManagerV2 instance
            config: Configuration options for matching behavior
        """
        self.state = state_manager
        self.config = config or {}

        # Default configuration
        self.fuzzy_threshold = self.config.get('fuzzy_threshold', 0.85)
        self.case_sensitive = self.config.get('case_sensitive', False)
        self.exact_name_match = self.config.get('exact_name_match', True)
        self.fuzzy_matching = self.config.get('fuzzy_matching', True)

    def link_all_items(self) -> List[ItemMatch]:
        """
        Link all unlinked items using intelligent matching strategies

        Returns:
            List of matches that were linked
        """
        logger.info("Starting intelligent item linking...")

        # Get unlinked items
        unlinked_paprika = self.state.get_unlinked_paprika_items()
        unlinked_skylight = self.state.get_unlinked_skylight_items()

        logger.info(f"Found {len(unlinked_paprika)} unlinked Paprika items, "
                   f"{len(unlinked_skylight)} unlinked Skylight items")

        if not unlinked_paprika or not unlinked_skylight:
            logger.info("No items to link")
            return []

        # Strategy 1: Exact name matching
        exact_matches = []
        if self.exact_name_match:
            exact_matches = self._find_exact_matches(unlinked_paprika, unlinked_skylight)
            logger.info(f"Found {len(exact_matches)} exact name matches")

        # Remove exact matches from unlinked lists
        linked_paprika_ids = {m.paprika_item.id for m in exact_matches}
        linked_skylight_ids = {m.skylight_item.id for m in exact_matches}

        remaining_paprika = [p for p in unlinked_paprika if p.id not in linked_paprika_ids]
        remaining_skylight = [s for s in unlinked_skylight if s.id not in linked_skylight_ids]

        # Strategy 2: Fuzzy matching
        fuzzy_matches = []
        if self.fuzzy_matching and remaining_paprika and remaining_skylight:
            fuzzy_matches = self._find_fuzzy_matches(remaining_paprika, remaining_skylight)
            logger.info(f"Found {len(fuzzy_matches)} fuzzy matches")

        # Apply all matches
        all_matches = exact_matches + fuzzy_matches
        applied_matches = []

        for match in all_matches:
            try:
                link = self.state.create_item_link(
                    match.paprika_item.id,
                    match.skylight_item.id,
                    match.confidence_score
                )

                applied_matches.append(match)
                logger.info(f"Linked: '{match.paprika_item.name}' ↔ '{match.skylight_item.name}' "
                           f"(confidence: {match.confidence_score:.2f}, reason: {match.match_reason})")

            except Exception as e:
                logger.error(f"Failed to link {match.paprika_item.name} ↔ {match.skylight_item.name}: {e}")

        logger.info(f"Successfully linked {len(applied_matches)} items")
        return applied_matches

    def _find_exact_matches(self, paprika_items: List[PaprikaItem],
                           skylight_items: List[SkylightItem]) -> List[ItemMatch]:
        """
        Find exact name matches, handling multiple items with same names

        Args:
            paprika_items: Unlinked Paprika items
            skylight_items: Unlinked Skylight items

        Returns:
            List of exact matches
        """
        matches = []

        # Group items by normalized name
        paprika_by_name = {}
        for item in paprika_items:
            name_key = self._normalize_name(item.name)
            if name_key not in paprika_by_name:
                paprika_by_name[name_key] = []
            paprika_by_name[name_key].append(item)

        skylight_by_name = {}
        for item in skylight_items:
            name_key = self._normalize_name(item.name)
            if name_key not in skylight_by_name:
                skylight_by_name[name_key] = []
            skylight_by_name[name_key].append(item)

        # Find exact matches
        for name_key in paprika_by_name:
            if name_key in skylight_by_name:
                paprika_group = paprika_by_name[name_key]
                skylight_group = skylight_by_name[name_key]

                # Handle different group sizes
                if len(paprika_group) == 1 and len(skylight_group) == 1:
                    # Perfect 1:1 match
                    matches.append(ItemMatch(
                        paprika_item=paprika_group[0],
                        skylight_item=skylight_group[0],
                        confidence_score=1.0,
                        match_reason="exact_name_perfect"
                    ))

                elif len(paprika_group) == len(skylight_group):
                    # Same count - use timing proximity
                    paired_matches = self._pair_by_timing(paprika_group, skylight_group)
                    for p_item, s_item, confidence in paired_matches:
                        matches.append(ItemMatch(
                            paprika_item=p_item,
                            skylight_item=s_item,
                            confidence_score=confidence,
                            match_reason="exact_name_timing"
                        ))

                else:
                    # Different counts - match best candidates
                    best_matches = self._match_best_candidates(paprika_group, skylight_group)
                    for p_item, s_item, confidence in best_matches:
                        matches.append(ItemMatch(
                            paprika_item=p_item,
                            skylight_item=s_item,
                            confidence_score=confidence,
                            match_reason="exact_name_best"
                        ))

        return matches

    def _find_fuzzy_matches(self, paprika_items: List[PaprikaItem],
                           skylight_items: List[SkylightItem]) -> List[ItemMatch]:
        """
        Find fuzzy matches for similar but not identical names

        Args:
            paprika_items: Remaining unlinked Paprika items
            skylight_items: Remaining unlinked Skylight items

        Returns:
            List of fuzzy matches above threshold
        """
        matches = []

        for p_item in paprika_items:
            best_match = None
            best_score = 0.0

            for s_item in skylight_items:
                # Calculate similarity
                similarity = self._calculate_similarity(p_item.name, s_item.name)

                if similarity >= self.fuzzy_threshold and similarity > best_score:
                    best_match = s_item
                    best_score = similarity

            if best_match:
                matches.append(ItemMatch(
                    paprika_item=p_item,
                    skylight_item=best_match,
                    confidence_score=best_score,
                    match_reason=f"fuzzy_match_{best_score:.2f}"
                ))

        # Remove duplicate Skylight matches (keep highest confidence)
        unique_matches = {}
        for match in matches:
            skylight_id = match.skylight_item.id
            if (skylight_id not in unique_matches or
                match.confidence_score > unique_matches[skylight_id].confidence_score):
                unique_matches[skylight_id] = match

        return list(unique_matches.values())

    def _pair_by_timing(self, paprika_group: List[PaprikaItem],
                       skylight_group: List[SkylightItem]) -> List[Tuple[PaprikaItem, SkylightItem, float]]:
        """
        Pair items with same names using timing proximity heuristics

        Args:
            paprika_group: Paprika items with same name
            skylight_group: Skylight items with same name

        Returns:
            List of (paprika_item, skylight_item, confidence) tuples
        """
        pairs = []

        # Sort by timestamps (most recent first)
        paprika_sorted = sorted(paprika_group,
                               key=lambda x: x.last_modified_at or x.created_at,
                               reverse=True)
        skylight_sorted = sorted(skylight_group,
                                key=lambda x: x.skylight_updated_at or x.skylight_created_at,
                                reverse=True)

        # Pair in order with decreasing confidence
        base_confidence = 0.9
        for i, (p_item, s_item) in enumerate(zip(paprika_sorted, skylight_sorted)):
            confidence = max(0.7, base_confidence - (i * 0.1))
            pairs.append((p_item, s_item, confidence))

        return pairs

    def _match_best_candidates(self, paprika_group: List[PaprikaItem],
                             skylight_group: List[SkylightItem]) -> List[Tuple[PaprikaItem, SkylightItem, float]]:
        """
        Match best candidates when group sizes are different

        Args:
            paprika_group: Paprika items with same name
            skylight_group: Skylight items with same name

        Returns:
            List of best matches
        """
        pairs = []

        # Use timing and checked status to find best matches
        for p_item in paprika_group:
            best_match = None
            best_score = 0.0

            for s_item in skylight_group:
                # Score based on checked status match and timing
                score = 0.6  # Base score for name match

                if p_item.checked == s_item.checked:
                    score += 0.2  # Bonus for matching checked status

                # Add timing bonus if both have timestamps
                if (p_item.last_modified_at and s_item.skylight_updated_at):
                    time_diff = abs((p_item.last_modified_at - s_item.skylight_updated_at).total_seconds())
                    if time_diff < 3600:  # Within 1 hour
                        score += 0.2

                if score > best_score:
                    best_match = s_item
                    best_score = score

            if best_match and best_score >= 0.6:
                pairs.append((p_item, best_match, best_score))

        return pairs

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two item names

        Args:
            name1: First name
            name2: Second name

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Normalize names
        norm1 = self._normalize_name(name1)
        norm2 = self._normalize_name(name2)

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, norm1, norm2).ratio()

    def _normalize_name(self, name: str) -> str:
        """
        Normalize item name for comparison

        Args:
            name: Original name

        Returns:
            Normalized name
        """
        if not self.case_sensitive:
            name = name.lower()

        # Remove extra whitespace
        name = ' '.join(name.split())

        # Additional normalizations can be added here
        # e.g., remove punctuation, handle plurals, etc.

        return name

    def get_linking_summary(self) -> dict:
        """
        Get summary of current linking status

        Returns:
            Dictionary with linking statistics
        """
        try:
            stats = self.state.get_sync_statistics()

            unlinked_paprika = self.state.get_unlinked_paprika_items()
            unlinked_skylight = self.state.get_unlinked_skylight_items()

            # Group unlinked items by name to identify potential matches
            paprika_names = {}
            for item in unlinked_paprika:
                name_key = self._normalize_name(item.name)
                if name_key not in paprika_names:
                    paprika_names[name_key] = 0
                paprika_names[name_key] += 1

            skylight_names = {}
            for item in unlinked_skylight:
                name_key = self._normalize_name(item.name)
                if name_key not in skylight_names:
                    skylight_names[name_key] = 0
                skylight_names[name_key] += 1

            potential_exact_matches = len(set(paprika_names.keys()) & set(skylight_names.keys()))

            return {
                'total_paprika_items': stats['paprika_items'],
                'total_skylight_items': stats['skylight_items'],
                'linked_items': stats['linked_items'],
                'unlinked_paprika': len(unlinked_paprika),
                'unlinked_skylight': len(unlinked_skylight),
                'potential_exact_matches': potential_exact_matches,
                'paprika_name_groups': len(paprika_names),
                'skylight_name_groups': len(skylight_names),
                'duplicate_paprika_names': sum(1 for count in paprika_names.values() if count > 1),
                'duplicate_skylight_names': sum(1 for count in skylight_names.values() if count > 1)
            }

        except Exception as e:
            logger.error(f"Failed to get linking summary: {e}")
            return {'error': str(e)}