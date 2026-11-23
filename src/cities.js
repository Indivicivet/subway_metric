export const cities = {
  taipei: {
    name: "Taipei",
    mode: "MRT",
    start: [121.517, 25.0468],
    view: [[121.418, 24.956], [121.631, 25.174]],
    credit: "MRT data",
    shortLineLabels: true,
  },
  london: {
    name: "London",
    mode: "Tube",
    start: [-0.12765, 51.50797],
    view: [[-0.614, 51.397], [0.253, 51.709]],
    credit: "Powered by TfL Open Data",
  },
  guangzhou: {
    name: "Guangzhou",
    mode: "Metro",
    start: [113.3158725, 23.1219809],
    view: [[113.09, 22.75], [113.87, 23.62]],
    minZoom: 8.5,
    credit: "Guangzhou data and estimates",
    timeLabel: "Estimated weekday",
  },
};

export const defaultCity = "taipei";
