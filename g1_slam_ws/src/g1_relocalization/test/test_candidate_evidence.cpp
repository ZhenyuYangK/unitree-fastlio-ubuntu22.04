#include "g1_relocalization/candidate_evidence.hpp"

#include <limits>
#include <gtest/gtest.h>

using g1_relocalization::CandidateEvidence;
using g1_relocalization::verifiedWinner;

TEST(CandidateEvidence, HighestScoreNeedsFullWindowAndComparison)
{
  std::vector<CandidateEvidence> bank(2, CandidateEvidence(3));
  for (int i = 0; i < 2; ++i) {bank[0].observe(true, .9, .98); bank[1].observe(true, .7, .8);}
  EXPECT_EQ(verifiedWinner(bank, .08), -1);
  bank[0].observe(true, .9, .98); bank[1].observe(true, .7, .8);
  EXPECT_EQ(verifiedWinner(bank, .08), 0);
  EXPECT_EQ(verifiedWinner(bank, .08, true), -1);
}

TEST(CandidateEvidence, BackupCanBeatOriginalFirstAndFailedFirst)
{
  std::vector<CandidateEvidence> bank(2, CandidateEvidence(3));
  for (int i = 0; i < 3; ++i) {bank[0].observe(true, .7, .8); bank[1].observe(true, .9, .98);}
  EXPECT_EQ(verifiedWinner(bank, .08), 1);
  for (int i = 0; i < 3; ++i) {bank[0].observe(false, .1, .2, true); bank[1].observe(true, .6, .9);}
  EXPECT_EQ(verifiedWinner(bank, .08), 1);
}

TEST(CandidateEvidence, SimilarStableLocationsRemainAmbiguous)
{
  std::vector<CandidateEvidence> bank(2, CandidateEvidence(3));
  for (int i = 0; i < 20; ++i) {
    bank[0].observe(true, .9); bank[1].observe(true, .89);
    EXPECT_EQ(verifiedWinner(bank, .08), -1);
  }
  EXPECT_EQ(bank[0].count(), 3u);
}

TEST(CandidateEvidence, MissingAndNonfiniteEvidenceCannotWin)
{
  std::vector<CandidateEvidence> bank(2, CandidateEvidence(3));
  for (int i = 0; i < 3; ++i) {bank[0].observe(true, .9);}
  EXPECT_EQ(verifiedWinner(bank, .08), -1);
  for (int i = 0; i < 3; ++i) {bank[1].observe(true, std::numeric_limits<double>::quiet_NaN());}
  EXPECT_EQ(verifiedWinner(bank, .08), -1);
  for (int i = 0; i < 3; ++i) {bank[1].observe(false, .1, .2, true);}
  EXPECT_EQ(verifiedWinner(bank, .08), 0);
  EXPECT_THROW(CandidateEvidence(1), std::invalid_argument);
}

TEST(CandidateEvidence, ResidualAdvantageWithoutNewCoverageCannotDisambiguateRooms)
{
  std::vector<CandidateEvidence> bank(2, CandidateEvidence(3));
  for (int i = 0; i < 3; ++i) {bank[0].observe(true, .85, 1.); bank[1].observe(true, .6, .96);}
  EXPECT_EQ(verifiedWinner(bank, .08), -1);
}

TEST(CandidateEvidence, OptimizerFailureDoesNotEraseCompetingGeometry)
{
  std::vector<CandidateEvidence> bank(2, CandidateEvidence(3));
  for (int i = 0; i < 3; ++i) {bank[0].observe(true, .9, 1.); bank[1].observe(false, .8, 1.);}
  EXPECT_EQ(verifiedWinner(bank, .08), -1);
  for (int i = 0; i < 3; ++i) {bank[1].observe(false, .5, .7);}
  EXPECT_EQ(verifiedWinner(bank, .08), 0);
}
