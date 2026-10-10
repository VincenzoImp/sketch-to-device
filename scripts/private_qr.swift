// Render a private setup link locally; no network or external QR service.
import Foundation
import CoreImage
import ImageIO

guard CommandLine.arguments.count == 3 else { exit(2) }
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
guard let data = try? Data(contentsOf: input), data.count < 2048,
      let filter = CIFilter(name: "CIQRCodeGenerator") else { exit(3) }
filter.setValue(data, forKey: "inputMessage")
filter.setValue("M", forKey: "inputCorrectionLevel")
guard let image = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 8, y: 8)),
      let bitmap = CIContext(options: [.useSoftwareRenderer: true]).createCGImage(image, from: image.extent),
      let destination = CGImageDestinationCreateWithURL(output as CFURL, "public.png" as CFString, 1, nil) else { exit(4) }
CGImageDestinationAddImage(destination, bitmap, nil)
guard CGImageDestinationFinalize(destination) else { exit(5) }
