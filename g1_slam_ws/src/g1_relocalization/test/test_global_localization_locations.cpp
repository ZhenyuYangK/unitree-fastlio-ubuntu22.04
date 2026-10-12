#include "g1_relocalization/global_matcher.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include <Eigen/Geometry>
#include <gtest/gtest.h>

namespace
{
using namespace g1_relocalization;
constexpr double kPi = 3.14159265358979323846;

struct Segment
{
  Eigen::Vector2f a, b;
};

std::vector<Segment> environment()
{
  // Connected asymmetric room/corridor geometry. Scan points below are ray
  // intersections sampled independently of the map, with true occlusion.
  return {
    {{-6.f, -5.f}, {8.f, -5.f}}, {{8.f, -5.f}, {8.f, -1.f}},
    {{8.f, -1.f}, {4.f, -1.f}}, {{4.f, -1.f}, {4.f, 6.f}},
    {{4.f, 6.f}, {-1.f, 6.f}}, {{-1.f, 6.f}, {-1.f, 3.f}},
    {{-1.f, 3.f}, {-6.f, 3.f}}, {{-6.f, 3.f}, {-6.f, -5.f}},
    {{-3.f, -3.f}, {-1.f, -3.f}}, {{-1.f, -3.f}, {-1.f, -1.f}},
    {{1.f, -2.f}, {3.f, -2.f}}, {{0.f, 1.f}, {2.f, 1.f}},
    {{2.f, 1.f}, {2.f, 2.4f}}, {{0.3f, 4.f}, {1.1f, 4.f}},
    {{1.1f, 4.f}, {1.1f, 5.f}}};
}

GlobalCloud::Ptr sampledMap()
{
  auto map = GlobalCloud::Ptr(new GlobalCloud);
  for (const auto & segment : environment()) {
    const int count = std::ceil((segment.b - segment.a).norm() / .11f);
    for (int i = 0; i <= count; ++i) {
      const Eigen::Vector2f xy = segment.a + float(i) / count * (segment.b - segment.a);
      for (float z = -.7f; z <= 1.6f; z += .13f) {
        GlobalPoint point;
        point.x = xy.x(); point.y = xy.y(); point.z = z; point.intensity = 1.f;
        map->push_back(point);
      }
    }
  }
  return map;
}

double cross(const Eigen::Vector2f & a, const Eigen::Vector2f & b)
{
  return double(a.x()) * b.y() - double(a.y()) * b.x();
}

Eigen::Matrix4f pose(float x, float y, float yaw_deg)
{
  Eigen::Matrix4f result = Eigen::Matrix4f::Identity();
  result.block<3, 3>(0, 0) = Eigen::AngleAxisf(yaw_deg * kPi / 180.f,
    Eigen::Vector3f::UnitZ()).toRotationMatrix();
  result(0, 3) = x; result(1, 3) = y;
  return result;
}

GlobalCloud::Ptr rayScan(
  const Eigen::Matrix4f & map_T_scan, double fov_deg = 280., double phase = .31,
  int changed_beam_stride = 0)
{
  auto scan = GlobalCloud::Ptr(new GlobalCloud);
  const Eigen::Vector2f origin = map_T_scan.block<2, 1>(0, 3);
  const Eigen::Matrix2f map_R_scan = map_T_scan.block<2, 2>(0, 0);
  const auto walls = environment();
  for (int beam = 0; beam < 640; ++beam) {
    const double angle = (-fov_deg / 2. + (beam + phase) * fov_deg / 640.) * kPi / 180.;
    const Eigen::Vector2f local_direction(std::cos(angle), std::sin(angle));
    const Eigen::Vector2f direction = map_R_scan * local_direction;
    double range = std::numeric_limits<double>::infinity();
    for (const auto & wall : walls) {
      const Eigen::Vector2f edge = wall.b - wall.a;
      const double denominator = cross(direction, edge);
      if (std::abs(denominator) < 1e-7) {continue;}
      const Eigen::Vector2f difference = wall.a - origin;
      const double distance = cross(difference, edge) / denominator;
      const double fraction = cross(difference, direction) / denominator;
      if (distance > .8 && fraction >= 0 && fraction <= 1) {
        range = std::min(range, distance);
      }
    }
    if (!std::isfinite(range) || range > 20.) {continue;}
    // Some beams hit a nearer temporary surface absent from the map. This
    // models changed geometry, rather than copies of map points plus noise.
    if (changed_beam_stride && beam % changed_beam_stride == 0 && range > 2.) {
      range *= .80;
    }
    for (int layer = 0; layer < 17; ++layer) {
      if ((beam + 3 * layer) % 11 == 0) {continue;}
      const double noisy_range = range + .015 * std::sin(beam * .73 + layer * .31 + phase);
      GlobalPoint point;
      point.x = noisy_range * local_direction.x();
      point.y = noisy_range * local_direction.y();
      point.z = -.65 + layer * .132 + .01 * std::cos(beam * .41 + layer * .91 + phase);
      point.intensity = 1.f;
      scan->push_back(point);
    }
  }
  return scan;
}

GlobalMatcherOptions settings()
{
  GlobalMatcherOptions options;
  options.use_search_bounds = true;
  options.min_x = -6.; options.max_x = 8.;
  options.min_y = -5.; options.max_y = 6.;
  options.time_budget_seconds = 30.;
  options.ndt_resolution = .8;
  options.min_scan_points = 100;
  return options;
}

void expectPose(const GlobalMatchResult & result, const Eigen::Matrix4f & expected)
{
  ASSERT_EQ(result.status, GlobalMatchStatus::SUCCESS) << result.reason;
  ASSERT_FALSE(result.candidates.empty());
  const auto & actual = result.candidates.front().map_T_scan;
  EXPECT_LT((actual.block<2, 1>(0, 3) - expected.block<2, 1>(0, 3)).norm(), .25);
  // Vertical walls constrain height less strongly than horizontal pose.
  EXPECT_LT(std::abs(actual(2, 3) - expected(2, 3)), .30);
  const Eigen::Matrix3f relative = expected.block<3, 3>(0, 0).transpose() *
    actual.block<3, 3>(0, 0);
  EXPECT_LT(std::abs(std::atan2(relative(1, 0), relative(0, 0))), 4. * kPi / 180.);
}

TEST(GlobalLocalizationLocations, ColdStartAcrossSeparatedLocationsAndYaws)
{
  GlobalMatcher matcher(sampledMap(), settings());
  for (const auto & expected : {
    pose(-4.5f, 1.f, 33.f), pose(6.f, -3.5f, -147.f),
    pose(2.8f, 4.6f, 109.f), pose(.6f, -.2f, -71.f)})
  {
    SCOPED_TRACE("x=" + std::to_string(expected(0, 3)) + " y=" +
      std::to_string(expected(1, 3)));
    const auto scan = rayScan(expected);
    ASSERT_TRUE(matcher.evaluate(scan, expected).acceptable);
    const auto result = matcher.search(scan);
    expectPose(result, expected);
    if (result.status == GlobalMatchStatus::SUCCESS) {
      EXPECT_TRUE(matcher.evaluate(rayScan(expected, 280., .77),
        result.candidates.front().map_T_scan).acceptable);
    }
  }
}

TEST(GlobalLocalizationLocations, PartiallyChangedGeometryStillNeedsUniqueSupportedPose)
{
  GlobalMatcher matcher(sampledMap(), settings());
  const auto expected = pose(.6f, -.2f, -71.f);
  const auto scan = rayScan(expected, 260., .31, 4);
  const auto quality = matcher.evaluate(scan, expected);
  ASSERT_TRUE(quality.acceptable) << "coverage=" << quality.coverage;
  EXPECT_LT(quality.coverage, .90);
  const auto result = matcher.search(scan);
  expectPose(result, expected);
}

TEST(GlobalLocalizationLocations, InsufficientFieldOfViewCannotAcceptAnArbitraryWallPose)
{
  GlobalMatcher matcher(sampledMap(), settings());
  const auto expected = pose(6.f, -3.5f, 0.f);
  // Only one flat wall: translation along the wall is unobservable. A search
  // must preserve ambiguity even though nearest-neighbour coverage is high.
  const auto scan = rayScan(expected, 50.);
  ASSERT_GE(matcher.evaluate(scan, expected).evaluated_points, 100u);
  const auto result = matcher.search(scan);
  EXPECT_NE(result.status, GlobalMatchStatus::SUCCESS) << result.reason;
}
}  // namespace
