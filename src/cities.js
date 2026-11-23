const cities = {
  taipei: {
    name: "Taipei",
    mode: "MRT",
    start: [121.517, 25.0468],
    view: [[121.418, 24.956], [121.631, 25.174]],
    credit: "MRT data",
  },
  london: {
    name: "London",
    mode: "Tube",
    start: [-0.12765, 51.50797],
    view: [[-0.614, 51.397], [0.253, 51.709]],
    credit: "Powered by TfL Open Data",
  },
};

const requested = new URLSearchParams(location.search).get("city");
export const cityId = Object.hasOwn(cities, requested) ? requested : "taipei";
export const city = cities[cityId];
